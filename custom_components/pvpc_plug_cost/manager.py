"""Integration engine for PVPC Plug Cost."""

from __future__ import annotations

import asyncio
from collections.abc import Callable
from datetime import datetime, timedelta
from decimal import Decimal
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import (
    ATTR_UNIT_OF_MEASUREMENT,
    EVENT_HOMEASSISTANT_STOP,
    STATE_UNAVAILABLE,
    STATE_UNKNOWN,
    UnitOfPower,
)
from homeassistant.core import CALLBACK_TYPE, HomeAssistant, callback
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.device import async_entity_id_to_device
from homeassistant.helpers.event import (
    async_track_state_change_event,
    async_track_time_change,
    async_track_time_interval,
)
from homeassistant.helpers.storage import Store
from homeassistant.util import dt as dt_util
from homeassistant.util.unit_conversion import PowerConverter

from .calculator import (
    EnergyCost,
    ZERO,
    accumulate_segment,
    billing_period_start,
    interpolate_power,
    period_boundaries,
    start_of_day,
    start_of_hour,
    start_of_year,
    to_decimal,
)
from .const import (
    DOMAIN,
    MAX_GAP,
    POWER_UNITS,
    PRICE_UNITS,
    SAVE_INTERVAL,
    STORAGE_VERSION,
)


class PVPCCostManager:
    """Calculate energy and cost totals for one smart plug."""

    def __init__(
        self,
        hass: HomeAssistant,
        entry: ConfigEntry,
        power_entity: str,
        price_entity: str,
        billing_day: int,
        scan_interval: timedelta,
    ) -> None:
        self.hass = hass
        self.entry = entry
        self.power_entity = power_entity
        self.price_entity = price_entity
        self.billing_day = billing_day
        self.scan_interval = scan_interval
        self._max_gap = max(MAX_GAP, scan_interval * 3)
        self.device_entry = async_entity_id_to_device(hass, power_entity)

        self._store = Store(hass, STORAGE_VERSION, f"{DOMAIN}.{entry.entry_id}")
        self._listeners: list[Callable[[], None]] = []
        self._unsubs: list[CALLBACK_TYPE] = []
        self._unsub_stop: CALLBACK_TYPE | None = None
        self._stopped = False
        self._save_lock = asyncio.Lock()

        self._hour_start: datetime | None = None
        self._hour_energy = ZERO
        self._hour_cost = ZERO
        self._day_start: datetime | None = None
        self._day_energy = ZERO
        self._day_cost = ZERO
        self._month_start: datetime | None = None
        self._month_energy = ZERO
        self._month_cost = ZERO
        self._year_start: datetime | None = None
        self._year_energy = ZERO
        self._year_cost = ZERO
        self._total_energy = ZERO
        self._total_cost = ZERO

        self._last_sample: datetime | None = None
        self._last_power_kw: Decimal | None = None
        self._last_price: Decimal | None = None
        self._power_available = False
        self._price_available = False
        self._last_save: datetime | None = None

    @property
    def hour_energy(self) -> Decimal:
        """Return energy accumulated during the current hour."""

        return self._hour_energy

    @property
    def hour_cost(self) -> Decimal:
        """Return cost accumulated during the current hour."""

        return self._hour_cost

    @property
    def hour_start(self) -> datetime | None:
        """Return the start of the current hour."""

        return self._hour_start

    @property
    def day_energy(self) -> Decimal:
        """Return energy accumulated during the current day."""

        return self._day_energy

    @property
    def day_cost(self) -> Decimal:
        """Return cost accumulated during the current day."""

        return self._day_cost

    @property
    def day_start(self) -> datetime | None:
        """Return the start of the current day."""

        return self._day_start

    @property
    def month_energy(self) -> Decimal:
        """Return energy accumulated during the current billing period."""

        return self._month_energy

    @property
    def month_cost(self) -> Decimal:
        """Return cost accumulated during the current billing period."""

        return self._month_cost

    @property
    def month_start(self) -> datetime | None:
        """Return the start of the current billing period."""

        return self._month_start

    @property
    def year_energy(self) -> Decimal:
        """Return energy accumulated during the current year."""

        return self._year_energy

    @property
    def year_cost(self) -> Decimal:
        """Return cost accumulated during the current year."""

        return self._year_cost

    @property
    def year_start(self) -> datetime | None:
        """Return the start of the current year."""

        return self._year_start

    @property
    def total_energy(self) -> Decimal:
        """Return energy accumulated since the integration was installed."""

        return self._total_energy

    @property
    def total_cost(self) -> Decimal:
        """Return cost accumulated since the integration was installed."""

        return self._total_cost

    @property
    def current_power_kw(self) -> Decimal | None:
        """Return the last sampled power in kW."""

        return self._last_power_kw

    @property
    def current_price(self) -> Decimal | None:
        """Return the last sampled energy price in EUR/kWh."""

        return self._last_price

    @property
    def current_cost_rate(self) -> Decimal | None:
        """Return the current cost rate in EUR/h."""

        if self._last_power_kw is None or self._last_price is None:
            return None
        return self._last_power_kw * self._last_price

    @property
    def last_sample(self) -> datetime | None:
        """Return the timestamp of the last sample in local time."""

        if self._last_sample is None:
            return None
        return dt_util.as_local(self._last_sample)

    @property
    def status(self) -> str:
        """Return a compact status for diagnostics."""

        if self._power_available and self._price_available:
            return "ok"
        if not self._power_available and not self._price_available:
            return "power_and_price_unavailable"
        if not self._power_available:
            return "power_unavailable"
        return "price_unavailable"

    @callback
    def async_add_listener(self, update_callback: Callable[[], None]) -> CALLBACK_TYPE:
        """Register an entity update callback."""

        self._listeners.append(update_callback)

        @callback
        def remove_listener() -> None:
            if update_callback in self._listeners:
                self._listeners.remove(update_callback)

        return remove_listener

    async def async_load(self) -> None:
        """Restore persisted totals and discard expired periods."""

        stored = await self._store.async_load()
        if isinstance(stored, dict):
            self._hour_start = self._parse_datetime(stored.get("hour_start"))
            self._hour_energy = to_decimal(stored.get("hour_energy")) or ZERO
            self._hour_cost = to_decimal(stored.get("hour_cost")) or ZERO
            self._day_start = self._parse_datetime(stored.get("day_start"))
            self._day_energy = to_decimal(stored.get("day_energy")) or ZERO
            self._day_cost = to_decimal(stored.get("day_cost")) or ZERO
            self._month_start = self._parse_datetime(stored.get("month_start"))
            self._month_energy = to_decimal(stored.get("month_energy")) or ZERO
            self._month_cost = to_decimal(stored.get("month_cost")) or ZERO
            self._year_start = self._parse_datetime(stored.get("year_start"))
            self._year_energy = to_decimal(stored.get("year_energy")) or ZERO
            self._year_cost = to_decimal(stored.get("year_cost")) or ZERO
            self._total_energy = to_decimal(stored.get("total_energy")) or ZERO
            self._total_cost = to_decimal(stored.get("total_cost")) or ZERO

        self._ensure_periods(dt_util.now())

    async def async_start(self) -> None:
        """Start listening to the source entities."""

        self._last_sample = None
        self._unsubs.extend(
            [
                async_track_state_change_event(
                    self.hass, [self.power_entity], self._handle_source_event
                ),
                async_track_state_change_event(
                    self.hass, [self.price_entity], self._handle_source_event
                ),
                async_track_time_interval(
                    self.hass, self._handle_tick, self.scan_interval
                ),
                async_track_time_change(
                    self.hass, self._handle_tick, minute=0, second=0
                ),
            ]
        )
        self._unsub_stop = self.hass.bus.async_listen_once(
            EVENT_HOMEASSISTANT_STOP, self._handle_hass_stop
        )
        self._async_sample()

    async def _handle_hass_stop(self, _event: Any) -> None:
        """Persist the latest totals when Home Assistant is stopping."""

        self._unsub_stop = None
        await self.async_stop()

    async def async_stop(self) -> None:
        """Stop listening and persist the latest totals."""

        if self._stopped:
            return
        self._stopped = True

        for unsub in self._unsubs:
            unsub()
        self._unsubs.clear()
        if self._unsub_stop is not None:
            self._unsub_stop()
            self._unsub_stop = None
        async with self._save_lock:
            await self._store.async_save(self._serialize())

    @callback
    def _handle_source_event(self, _event: Any) -> None:
        self._async_sample()

    @callback
    def _handle_tick(self, now: datetime) -> None:
        self._async_sample(now)

    @callback
    def _async_sample(self, now: datetime | None = None) -> None:
        """Integrate since the previous sample and notify entities."""

        current = dt_util.as_utc(now) if now is not None else dt_util.utcnow()
        local_current = dt_util.as_local(current)
        power = self._read_power_kw()
        price = self._read_price()
        self._power_available = power is not None
        self._price_available = price is not None

        if self._last_sample is None:
            self._last_sample = current
            self._last_power_kw = power
            self._last_price = price
            self._ensure_periods(local_current)
            self._notify()
            return

        elapsed = (current - self._last_sample).total_seconds()
        if elapsed <= 0:
            return

        if elapsed > self._max_gap.total_seconds():
            self._last_sample = current
            self._last_power_kw = power
            self._last_price = price
            self._ensure_periods(local_current)
            self._notify()
            return

        previous_power = self._last_power_kw
        previous_price = self._last_price
        if (
            previous_power is None
            or power is None
            or previous_price is None
            or price is None
        ):
            self._last_sample = current
            self._last_power_kw = power
            self._last_price = price if price is not None else previous_price
            self._ensure_periods(local_current)
            self._notify()
            return

        local_boundaries = period_boundaries(
            dt_util.as_local(self._last_sample),
            local_current,
            self.billing_day,
        )
        boundaries = [dt_util.as_utc(boundary) for boundary in local_boundaries]
        total_seconds = Decimal(str(elapsed))
        cursor = self._last_sample
        power_at_cursor = previous_power
        segment_price = previous_price

        for boundary in [*boundaries, current]:
            segment_seconds = Decimal(str((boundary - cursor).total_seconds()))
            if segment_seconds <= ZERO:
                continue

            if boundary == current:
                power_at_boundary = power
            else:
                elapsed_fraction = Decimal(
                    str((boundary - self._last_sample).total_seconds())
                ) / total_seconds
                power_at_boundary = interpolate_power(
                    previous_power, power, elapsed_fraction
                )

            result = accumulate_segment(
                power_at_cursor,
                power_at_boundary,
                segment_price,
                cursor,
                boundary,
            )
            self._add_accumulation(cursor, result)

            cursor = boundary
            power_at_cursor = power_at_boundary
            segment_price = price if price is not None else previous_price

        self._last_sample = current
        self._last_power_kw = power
        self._last_price = price if price is not None else previous_price
        self._ensure_periods(local_current)
        self._schedule_save()
        self._notify()

    def _read_power_kw(self) -> Decimal | None:
        state = self.hass.states.get(self.power_entity)
        if state is None or state.state in (STATE_UNAVAILABLE, STATE_UNKNOWN):
            return None

        value = to_decimal(state.state)
        unit = state.attributes.get(ATTR_UNIT_OF_MEASUREMENT)
        if value is None or unit not in POWER_UNITS:
            return None

        try:
            watts = PowerConverter.convert(float(value), unit, UnitOfPower.WATT)
        except (HomeAssistantError, OverflowError, TypeError, ValueError):
            return None
        return Decimal(str(watts)) / Decimal(1000)

    def _read_price(self) -> Decimal | None:
        state = self.hass.states.get(self.price_entity)
        if state is None or state.state in (STATE_UNAVAILABLE, STATE_UNKNOWN):
            return None

        unit = state.attributes.get(ATTR_UNIT_OF_MEASUREMENT)
        if unit not in PRICE_UNITS:
            return None
        return to_decimal(state.state)

    @staticmethod
    def _start_key(value: datetime | None) -> datetime | None:
        """Return the UTC instant of a period start."""

        if value is None:
            return None
        return dt_util.as_utc(value)

    def _add_accumulation(self, when: datetime, result: EnergyCost) -> None:
        local_when = dt_util.as_local(when)
        hour = start_of_hour(local_when)
        day = start_of_day(local_when)
        month = billing_period_start(local_when, self.billing_day)
        year = start_of_year(local_when)

        hour_key = dt_util.as_utc(hour)
        day_key = dt_util.as_utc(day)
        month_key = dt_util.as_utc(month)
        year_key = dt_util.as_utc(year)

        hour_start_key = self._start_key(self._hour_start)
        if hour_start_key is None or hour_key > hour_start_key:
            self._hour_start = hour
            self._hour_energy = ZERO
            self._hour_cost = ZERO
            hour_start_key = hour_key

        day_start_key = self._start_key(self._day_start)
        if day_start_key is None or day_key > day_start_key:
            self._day_start = day
            self._day_energy = ZERO
            self._day_cost = ZERO
            day_start_key = day_key

        month_start_key = self._start_key(self._month_start)
        if month_start_key is None or month_key > month_start_key:
            self._month_start = month
            self._month_energy = ZERO
            self._month_cost = ZERO
            month_start_key = month_key

        year_start_key = self._start_key(self._year_start)
        if year_start_key is None or year_key > year_start_key:
            self._year_start = year
            self._year_energy = ZERO
            self._year_cost = ZERO
            year_start_key = year_key

        if hour_key == hour_start_key:
            self._hour_energy += result.energy_kwh
            self._hour_cost += result.cost_eur

        if day_key == day_start_key:
            self._day_energy += result.energy_kwh
            self._day_cost += result.cost_eur

        if month_key == month_start_key:
            self._month_energy += result.energy_kwh
            self._month_cost += result.cost_eur

        if year_key == year_start_key:
            self._year_energy += result.energy_kwh
            self._year_cost += result.cost_eur

        self._total_energy += result.energy_kwh
        self._total_cost += result.cost_eur

    def _ensure_periods(self, now: datetime) -> None:
        hour = start_of_hour(now)
        day = start_of_day(now)
        month = billing_period_start(now, self.billing_day)
        year = start_of_year(now)

        if self._start_key(self._hour_start) != self._start_key(hour):
            self._hour_start = hour
            self._hour_energy = ZERO
            self._hour_cost = ZERO

        if self._start_key(self._day_start) != self._start_key(day):
            self._day_start = day
            self._day_energy = ZERO
            self._day_cost = ZERO

        if self._start_key(self._month_start) != self._start_key(month):
            self._month_start = month
            self._month_energy = ZERO
            self._month_cost = ZERO

        if self._start_key(self._year_start) != self._start_key(year):
            self._year_start = year
            self._year_energy = ZERO
            self._year_cost = ZERO

    def _schedule_save(self, force: bool = False) -> None:
        now = dt_util.utcnow()
        if (
            not force
            and self._last_save is not None
            and now - self._last_save < SAVE_INTERVAL
        ):
            return
        self._last_save = now
        self.hass.async_create_task(self._async_persist())

    async def _async_persist(self) -> None:
        """Write the latest totals to the store."""

        async with self._save_lock:
            await self._store.async_save(self._serialize())

    def _serialize(self) -> dict[str, Any]:
        return {
            "hour_start": self._hour_start.isoformat() if self._hour_start else None,
            "hour_energy": str(self._hour_energy),
            "hour_cost": str(self._hour_cost),
            "day_start": self._day_start.isoformat() if self._day_start else None,
            "day_energy": str(self._day_energy),
            "day_cost": str(self._day_cost),
            "month_start": (
                self._month_start.isoformat() if self._month_start else None
            ),
            "month_energy": str(self._month_energy),
            "month_cost": str(self._month_cost),
            "year_start": self._year_start.isoformat() if self._year_start else None,
            "year_energy": str(self._year_energy),
            "year_cost": str(self._year_cost),
            "total_energy": str(self._total_energy),
            "total_cost": str(self._total_cost),
        }

    @staticmethod
    def _parse_datetime(value: Any) -> datetime | None:
        if not isinstance(value, str):
            return None
        parsed = dt_util.parse_datetime(value)
        if parsed is None:
            return None
        return dt_util.as_local(parsed)

    @callback
    def _notify(self) -> None:
        for listener in list(self._listeners):
            if listener in self._listeners:
                listener()
