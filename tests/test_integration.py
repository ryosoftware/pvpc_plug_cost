"""Integration tests for PVPC Plug Cost."""

from __future__ import annotations

from datetime import datetime, timedelta
from decimal import Decimal
import time
from zoneinfo import ZoneInfo

import pytest

from homeassistant.config_entries import ConfigEntryState
from homeassistant.const import CONF_NAME, EVENT_HOMEASSISTANT_STOP
from homeassistant.data_entry_flow import FlowResultType
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers import entity_registry as er
from homeassistant.util import dt as dt_util
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.pvpc_plug_cost.config_flow import _user_schema
from custom_components.pvpc_plug_cost.const import (
    CONF_BILLING_DAY,
    CONF_POWER_ENTITY,
    CONF_PRICE_ENTITY,
    CONF_SCAN_INTERVAL,
    DEFAULT_PRICE_ENTITY,
    DOMAIN,
)


async def _setup_entry(
    hass,
    power_entity: str = "sensor.plug_power",
    title: str = "Plug",
    price_entity: str = DEFAULT_PRICE_ENTITY,
    price: str = "0.10",
) -> MockConfigEntry:
    hass.states.async_set(
        power_entity,
        "1000",
        {"unit_of_measurement": "W", "device_class": "power"},
    )
    hass.states.async_set(
        price_entity,
        price,
        {"unit_of_measurement": "€/kWh"},
    )

    entry = MockConfigEntry(
        domain=DOMAIN,
        title=title,
        unique_id=f"{power_entity}_{price_entity}",
        data={
            CONF_POWER_ENTITY: power_entity,
            CONF_PRICE_ENTITY: price_entity,
            CONF_BILLING_DAY: 1,
            CONF_SCAN_INTERVAL: 60,
        },
    )
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    return entry


async def test_setup_and_accumulation(hass) -> None:
    entry = await _setup_entry(hass)

    assert entry.state is ConfigEntryState.LOADED
    manager = entry.runtime_data
    assert manager.current_power_kw == Decimal("1.0")

    start = dt_util.utcnow().replace(hour=12, minute=0, second=0, microsecond=0)
    start += timedelta(days=1)
    manager._last_sample = start
    manager._last_power_kw = Decimal("1")
    manager._last_price = Decimal("0.10")
    manager._max_gap = timedelta(hours=1)
    manager._async_sample(start + timedelta(minutes=30))
    await hass.async_block_till_done()

    assert manager.day_energy == Decimal("0.5")
    assert manager.day_cost == Decimal("0.05")

    registry = er.async_get(hass)
    entities = {
        entity.unique_id: entity.entity_id
        for entity in er.async_entries_for_config_entry(registry, entry.entry_id)
    }

    cost_entity_id = entities[f"{entry.entry_id}_cost_today"]
    energy_entity_id = entities[f"{entry.entry_id}_energy_today"]
    hour_cost_entity_id = entities[f"{entry.entry_id}_cost_current_hour"]
    hour_energy_entity_id = entities[f"{entry.entry_id}_energy_current_hour"]
    last_hour_cost_entity_id = entities[f"{entry.entry_id}_cost_last_hour"]
    last_hour_energy_entity_id = entities[f"{entry.entry_id}_energy_last_hour"]
    month_cost_entity_id = entities[f"{entry.entry_id}_cost_current_month"]
    month_energy_entity_id = entities[f"{entry.entry_id}_energy_current_month"]
    last_month_cost_entity_id = entities[f"{entry.entry_id}_cost_last_month"]
    last_month_energy_entity_id = entities[f"{entry.entry_id}_energy_last_month"]
    year_cost_entity_id = entities[f"{entry.entry_id}_cost_current_year"]
    year_energy_entity_id = entities[f"{entry.entry_id}_energy_current_year"]
    total_cost_entity_id = entities[f"{entry.entry_id}_cost_total"]
    total_energy_entity_id = entities[f"{entry.entry_id}_energy_total"]

    cost_state = hass.states.get(cost_entity_id)
    energy_state = hass.states.get(energy_entity_id)
    assert cost_state is not None
    assert energy_state is not None
    assert Decimal(cost_state.state) == Decimal("0.05")
    assert Decimal(energy_state.state) == Decimal("0.5")
    assert cost_state.attributes["unit_of_measurement"] == "€"
    assert cost_state.attributes["device_class"] == "monetary"
    assert "state_class" not in cost_state.attributes
    assert cost_state.attributes["source_power_entity"] == "sensor.plug_power"
    assert cost_state.attributes["source_price_entity"] == DEFAULT_PRICE_ENTITY

    for entity_id in (
        hour_cost_entity_id,
        hour_energy_entity_id,
        last_hour_cost_entity_id,
        last_hour_energy_entity_id,
        month_cost_entity_id,
        month_energy_entity_id,
        last_month_cost_entity_id,
        last_month_energy_entity_id,
        year_cost_entity_id,
        year_energy_entity_id,
    ):
        state = hass.states.get(entity_id)
        assert state is not None
        assert "state_class" not in state.attributes
        assert "last_reset" not in state.attributes

    assert Decimal(hass.states.get(hour_cost_entity_id).state) == Decimal("0.05")
    assert Decimal(hass.states.get(hour_energy_entity_id).state) == Decimal("0.5")
    assert Decimal(hass.states.get(last_hour_cost_entity_id).state) == Decimal("0")
    assert Decimal(hass.states.get(last_hour_energy_entity_id).state) == Decimal("0")
    assert Decimal(hass.states.get(month_cost_entity_id).state) == Decimal("0.05")
    assert Decimal(hass.states.get(month_energy_entity_id).state) == Decimal("0.5")
    assert Decimal(hass.states.get(last_month_cost_entity_id).state) == Decimal("0")
    assert Decimal(hass.states.get(last_month_energy_entity_id).state) == Decimal("0")
    assert Decimal(hass.states.get(year_cost_entity_id).state) == Decimal("0.05")
    assert Decimal(hass.states.get(year_energy_entity_id).state) == Decimal("0.5")

    total_cost_state = hass.states.get(total_cost_entity_id)
    total_energy_state = hass.states.get(total_energy_entity_id)
    assert Decimal(total_cost_state.state) == Decimal("0.05")
    assert Decimal(total_energy_state.state) == Decimal("0.5")
    assert total_cost_state.attributes["state_class"] == "total"
    assert total_energy_state.attributes["state_class"] == "total_increasing"
    assert "last_reset" not in total_cost_state.attributes
    assert "last_reset" not in total_energy_state.attributes


async def test_entity_ids_use_english_keys(hass) -> None:
    hass.config.language = "es"
    entry = await _setup_entry(hass, title="Lavadora")

    registry = er.async_get(hass)
    entities = {
        entity.unique_id: entity
        for entity in er.async_entries_for_config_entry(registry, entry.entry_id)
    }

    assert (
        entities[f"{entry.entry_id}_cost_today"].entity_id
        == "sensor.lavadora_cost_today"
    )
    assert (
        entities[f"{entry.entry_id}_cost_today"].original_name == "Coste de hoy"
    )
    assert (
        entities[f"{entry.entry_id}_energy_total"].entity_id
        == "sensor.lavadora_energy_total"
    )
    assert (
        entities[f"{entry.entry_id}_cost_current_billing_period"].entity_id
        == "sensor.lavadora_cost_current_billing_period"
    )
    assert (
        entities[f"{entry.entry_id}_cost_last_hour"].entity_id
        == "sensor.lavadora_cost_last_hour"
    )
    assert (
        entities[f"{entry.entry_id}_energy_last_hour"].entity_id
        == "sensor.lavadora_energy_last_hour"
    )
    assert (
        entities[f"{entry.entry_id}_energy_last_hour"].original_name
        == "Energía de la última hora completa"
    )
    assert (
        entities[f"{entry.entry_id}_cost_current_month"].entity_id
        == "sensor.lavadora_cost_current_month"
    )
    assert (
        entities[f"{entry.entry_id}_energy_current_month"].entity_id
        == "sensor.lavadora_energy_current_month"
    )
    assert (
        entities[f"{entry.entry_id}_cost_last_month"].entity_id
        == "sensor.lavadora_cost_last_month"
    )
    assert (
        entities[f"{entry.entry_id}_energy_last_month"].entity_id
        == "sensor.lavadora_energy_last_month"
    )
    assert (
        entities[f"{entry.entry_id}_cost_last_month"].original_name
        == "Coste del mes anterior"
    )


async def test_multiple_plugs_are_independent(hass) -> None:
    entry_one = await _setup_entry(
        hass, "sensor.plug_one_power", "Plug one"
    )
    entry_two = await _setup_entry(
        hass, "sensor.plug_two_power", "Plug two"
    )

    assert entry_one.entry_id != entry_two.entry_id

    hass.states.async_set(
        "sensor.plug_two_power",
        "2000",
        {"unit_of_measurement": "W", "device_class": "power"},
    )

    start = dt_util.utcnow().replace(hour=12, minute=0, second=0, microsecond=0)
    start += timedelta(days=1)

    for entry in (entry_one, entry_two):
        manager = entry.runtime_data
        manager._last_sample = start
        manager._last_power_kw = (
            Decimal("1") if entry is entry_one else Decimal("2")
        )
        manager._last_price = Decimal("0.10")
        manager._max_gap = timedelta(hours=1)
        manager._async_sample(start + timedelta(minutes=30))

    await hass.async_block_till_done()

    assert entry_one.runtime_data.day_energy == Decimal("0.5")
    assert entry_two.runtime_data.day_energy == Decimal("1.0")

    registry = er.async_get(hass)
    ids_one = {
        entity.entity_id
        for entity in er.async_entries_for_config_entry(
            registry, entry_one.entry_id
        )
    }
    ids_two = {
        entity.entity_id
        for entity in er.async_entries_for_config_entry(
            registry, entry_two.entry_id
        )
    }
    assert ids_one
    assert ids_two
    assert ids_one.isdisjoint(ids_two)


async def test_midnight_split_and_price_change(hass) -> None:
    entry = await _setup_entry(hass)
    manager = entry.runtime_data

    local_midnight = dt_util.start_of_local_day(
        dt_util.now() + timedelta(days=1)
    )
    start = dt_util.as_utc(local_midnight - timedelta(minutes=10))

    manager._last_sample = start
    manager._last_power_kw = Decimal("1")
    manager._last_price = Decimal("0.10")
    manager._max_gap = timedelta(hours=1)
    hass.states.async_set(
        DEFAULT_PRICE_ENTITY,
        "0.20",
        {"unit_of_measurement": "€/kWh"},
    )

    manager._async_sample(dt_util.as_utc(local_midnight))
    await hass.async_block_till_done()
    manager._async_sample(
        dt_util.as_utc(local_midnight + timedelta(minutes=10))
    )
    await hass.async_block_till_done()

    assert manager.day_start == local_midnight
    assert float(manager.day_energy) == pytest.approx(1 / 6)
    assert float(manager.day_cost) == pytest.approx((1 / 6) * 0.20)
    assert float(manager.month_energy) == pytest.approx(1 / 3)
    assert float(manager.month_cost) == pytest.approx(
        (1 / 6) * 0.10 + (1 / 6) * 0.20
    )


async def test_unavailable_power_does_not_accumulate(hass) -> None:
    entry = await _setup_entry(hass)
    manager = entry.runtime_data

    start = dt_util.utcnow().replace(hour=12, minute=0, second=0, microsecond=0)
    start += timedelta(days=1)
    manager._last_sample = start
    manager._last_power_kw = Decimal("1")
    manager._last_price = Decimal("0.10")

    hass.states.async_set("sensor.plug_power", "unavailable")
    manager._async_sample(start + timedelta(minutes=30))
    await hass.async_block_till_done()

    assert manager.day_energy == Decimal("0")


async def test_day_rollover_resets_totals(hass) -> None:
    entry = await _setup_entry(hass)
    manager = entry.runtime_data

    manager._day_start = dt_util.now() - timedelta(days=1)
    manager._day_energy = Decimal("5")
    manager._day_cost = Decimal("1")
    manager._ensure_periods(dt_util.now())

    assert manager.day_energy == Decimal("0")
    assert manager.day_cost == Decimal("0")


async def test_billing_period_rollover_resets_totals(hass) -> None:
    entry = await _setup_entry(hass)
    manager = entry.runtime_data

    manager.billing_day = 31
    manager._month_start = dt_util.now() - timedelta(days=40)
    manager._month_energy = Decimal("5")
    manager._month_cost = Decimal("1")
    manager._ensure_periods(dt_util.now())

    assert manager.month_energy == Decimal("0")
    assert manager.month_cost == Decimal("0")


async def test_hour_accumulation_resets_at_hour_boundary(hass) -> None:
    entry = await _setup_entry(hass)
    manager = entry.runtime_data

    local_hour = dt_util.start_of_local_day(
        dt_util.now() + timedelta(days=1)
    ) + timedelta(hours=12)
    start = dt_util.as_utc(local_hour - timedelta(minutes=30))
    end = dt_util.as_utc(local_hour + timedelta(minutes=30))

    manager._last_sample = start
    manager._last_power_kw = Decimal("1")
    manager._last_price = Decimal("0.10")
    manager._max_gap = timedelta(hours=2)
    manager._async_sample(end)
    await hass.async_block_till_done()

    assert manager.hour_start == local_hour
    assert manager.hour_energy == Decimal("0.5")
    assert manager.hour_cost == Decimal("0.05")
    assert manager.day_energy == Decimal("1.0")


async def test_left_method_uses_start_power(hass) -> None:
    entry = await _setup_entry(hass)
    manager = entry.runtime_data

    local_start = dt_util.start_of_local_day(
        dt_util.now() + timedelta(days=1)
    ) + timedelta(hours=12)
    start = dt_util.as_utc(local_start)

    manager._last_sample = start
    manager._last_power_kw = Decimal("1")
    manager._last_price = Decimal("0.10")
    manager._max_gap = timedelta(hours=1)
    hass.states.async_set(
        "sensor.plug_power",
        "2000",
        {"unit_of_measurement": "W", "device_class": "power"},
    )

    manager._async_sample(start + timedelta(minutes=30))
    await hass.async_block_till_done()

    assert manager.day_energy == Decimal("0.5")
    assert manager.day_cost == Decimal("0.05")
    assert manager.total_energy == Decimal("0.5")
    assert manager.current_power_kw == Decimal("2")


async def test_left_method_uses_start_values_across_hour_boundary(hass) -> None:
    entry = await _setup_entry(hass)
    manager = entry.runtime_data

    local_hour = dt_util.start_of_local_day(
        dt_util.now() + timedelta(days=1)
    ) + timedelta(hours=12)
    start = dt_util.as_utc(local_hour - timedelta(minutes=30))
    end = dt_util.as_utc(local_hour + timedelta(minutes=30))

    manager._last_sample = start
    manager._last_power_kw = Decimal("1")
    manager._last_price = Decimal("0.10")
    manager._max_gap = timedelta(hours=2)

    hass.states.async_set(
        "sensor.plug_power",
        "2000",
        {"unit_of_measurement": "W", "device_class": "power"},
    )
    hass.states.async_set(
        DEFAULT_PRICE_ENTITY,
        "0.20",
        {"unit_of_measurement": "€/kWh"},
    )

    manager._async_sample(end)
    await hass.async_block_till_done()

    assert manager.last_hour_start == local_hour - timedelta(hours=1)
    assert manager.last_hour_energy == Decimal("0.5")
    assert manager.last_hour_cost == Decimal("0.05")
    assert manager.hour_energy == Decimal("0.5")
    assert manager.hour_cost == Decimal("0.05")
    assert manager.day_energy == Decimal("1.0")
    assert manager.day_cost == Decimal("0.10")
    assert manager.current_power_kw == Decimal("2")
    assert manager.current_price == Decimal("0.20")


async def test_last_hour_accumulation_updates_at_hour_boundary(hass) -> None:
    entry = await _setup_entry(hass)
    manager = entry.runtime_data

    local_hour = dt_util.start_of_local_day(
        dt_util.now() + timedelta(days=1)
    ) + timedelta(hours=12)
    start = dt_util.as_utc(local_hour - timedelta(minutes=30))
    end = dt_util.as_utc(local_hour + timedelta(minutes=30))

    manager._last_sample = start
    manager._last_power_kw = Decimal("1")
    manager._last_price = Decimal("0.10")
    manager._max_gap = timedelta(hours=2)
    manager._async_sample(end)
    await hass.async_block_till_done()

    assert manager.last_hour_start == local_hour - timedelta(hours=1)
    assert manager.last_hour_energy == Decimal("0.5")
    assert manager.last_hour_cost == Decimal("0.05")
    assert manager.hour_start == local_hour
    assert manager.hour_energy == Decimal("0.5")
    assert manager.hour_cost == Decimal("0.05")


async def test_last_hour_promotes_sample_at_hour_boundary(hass) -> None:
    entry = await _setup_entry(hass)
    manager = entry.runtime_data

    local_hour = dt_util.start_of_local_day(
        dt_util.now() + timedelta(days=1)
    ) + timedelta(hours=12)
    start = dt_util.as_utc(local_hour - timedelta(minutes=30))

    manager._last_sample = start
    manager._last_power_kw = Decimal("1")
    manager._last_price = Decimal("0.10")
    manager._max_gap = timedelta(hours=2)
    manager._async_sample(dt_util.as_utc(local_hour))
    await hass.async_block_till_done()

    assert manager.last_hour_start == local_hour - timedelta(hours=1)
    assert manager.last_hour_energy == Decimal("0.5")
    assert manager.last_hour_cost == Decimal("0.05")
    assert manager.hour_start == local_hour
    assert manager.hour_energy == Decimal("0")
    assert manager.hour_cost == Decimal("0")


async def test_last_hour_with_multi_hour_gap(hass) -> None:
    entry = await _setup_entry(hass)
    manager = entry.runtime_data

    local_hour = dt_util.start_of_local_day(
        dt_util.now() + timedelta(days=1)
    ) + timedelta(hours=12)
    start = dt_util.as_utc(local_hour - timedelta(hours=2, minutes=30))
    end = dt_util.as_utc(local_hour + timedelta(minutes=30))

    manager._last_sample = start
    manager._last_power_kw = Decimal("1")
    manager._last_price = Decimal("0.10")
    manager._max_gap = timedelta(hours=4)
    manager._async_sample(end)
    await hass.async_block_till_done()

    assert manager.last_hour_start == local_hour - timedelta(hours=1)
    assert manager.last_hour_energy == Decimal("1.0")
    assert manager.last_hour_cost == Decimal("0.10")
    assert manager.hour_start == local_hour
    assert manager.hour_energy == Decimal("0.5")


async def test_last_hour_is_persisted_and_restored(hass) -> None:
    entry = await _setup_entry(hass)
    manager = entry.runtime_data

    local_hour = dt_util.start_of_local_day(
        dt_util.now() + timedelta(days=1)
    ) + timedelta(hours=12)
    start = dt_util.as_utc(local_hour - timedelta(minutes=30))
    end = dt_util.as_utc(local_hour + timedelta(minutes=30))

    manager._last_sample = start
    manager._last_power_kw = Decimal("1")
    manager._last_price = Decimal("0.10")
    manager._max_gap = timedelta(hours=2)
    manager._async_sample(end)
    await hass.async_block_till_done()

    hass.bus.async_fire(EVENT_HOMEASSISTANT_STOP)
    await hass.async_block_till_done()

    stored = await manager._store.async_load()
    assert stored is not None
    assert Decimal(stored["last_hour_energy"]) == Decimal("0.5")
    assert Decimal(stored["last_hour_cost"]) == Decimal("0.05")
    assert stored["last_hour_start"] == (local_hour - timedelta(hours=1)).isoformat()

    manager._last_hour_start = None
    manager._last_hour_energy = Decimal("0")
    manager._last_hour_cost = Decimal("0")
    await manager.async_load()

    assert manager.last_hour_start == local_hour - timedelta(hours=1)
    assert manager.last_hour_energy == Decimal("0.5")
    assert manager.last_hour_cost == Decimal("0.05")


async def test_calendar_month_rollover_promotes_and_resets(hass) -> None:
    entry = await _setup_entry(hass)
    manager = entry.runtime_data

    now = dt_util.now()
    if now.month == 12:
        month_start = now.replace(
            year=now.year + 1,
            month=1,
            day=1,
            hour=0,
            minute=0,
            second=0,
            microsecond=0,
        )
    else:
        month_start = now.replace(
            month=now.month + 1,
            day=1,
            hour=0,
            minute=0,
            second=0,
            microsecond=0,
        )
    previous_start = (month_start - timedelta(days=1)).replace(
        day=1, hour=0, minute=0, second=0, microsecond=0
    )

    manager._calendar_month_start = previous_start
    manager._calendar_month_energy = Decimal("1")
    manager._calendar_month_cost = Decimal("0.10")
    manager._last_sample = dt_util.as_utc(month_start - timedelta(minutes=30))
    manager._last_power_kw = Decimal("1")
    manager._last_price = Decimal("0.10")
    manager._max_gap = timedelta(hours=2)
    manager._async_sample(dt_util.as_utc(month_start + timedelta(minutes=30)))
    await hass.async_block_till_done()

    assert manager.calendar_month_start == month_start
    assert manager.calendar_month_energy == Decimal("0.5")
    assert manager.calendar_month_cost == Decimal("0.05")
    assert manager.last_month_start == previous_start
    assert manager.last_month_energy == Decimal("1.5")
    assert manager.last_month_cost == Decimal("0.15")


async def test_last_month_is_promoted_on_load(hass) -> None:
    entry = await _setup_entry(hass)
    manager = entry.runtime_data

    current_start = dt_util.now().replace(
        day=1, hour=0, minute=0, second=0, microsecond=0
    )
    previous_start = (current_start - timedelta(days=1)).replace(
        day=1, hour=0, minute=0, second=0, microsecond=0
    )

    await manager._store.async_save(
        {
            "calendar_month_start": previous_start.isoformat(),
            "calendar_month_energy": "5",
            "calendar_month_cost": "1",
        }
    )
    await manager.async_load()

    assert manager.calendar_month_start == current_start
    assert manager.calendar_month_energy == Decimal("0")
    assert manager.calendar_month_cost == Decimal("0")
    assert manager.last_month_start == previous_start
    assert manager.last_month_energy == Decimal("5")
    assert manager.last_month_cost == Decimal("1")


async def test_stale_stored_month_is_not_promoted(hass) -> None:
    entry = await _setup_entry(hass)
    manager = entry.runtime_data

    current_start = dt_util.now().replace(
        day=1, hour=0, minute=0, second=0, microsecond=0
    )
    stale_start = (current_start - timedelta(days=40)).replace(
        day=1, hour=0, minute=0, second=0, microsecond=0
    )

    await manager._store.async_save(
        {
            "calendar_month_start": stale_start.isoformat(),
            "calendar_month_energy": "5",
            "calendar_month_cost": "1",
            "last_month_start": stale_start.isoformat(),
            "last_month_energy": "4",
            "last_month_cost": "0.5",
        }
    )
    await manager.async_load()

    assert manager.calendar_month_start == current_start
    assert manager.calendar_month_energy == Decimal("0")
    assert manager.last_month_start is None
    assert manager.last_month_energy == Decimal("0")
    assert manager.last_month_cost == Decimal("0")


async def test_year_accumulation_resets_at_new_year(hass) -> None:
    entry = await _setup_entry(hass)
    manager = entry.runtime_data

    now = dt_util.now()
    next_year = now.replace(
        year=now.year + 1,
        month=1,
        day=1,
        hour=0,
        minute=0,
        second=0,
        microsecond=0,
    )
    start = dt_util.as_utc(next_year - timedelta(minutes=30))
    end = dt_util.as_utc(next_year + timedelta(minutes=30))

    manager._last_sample = start
    manager._last_power_kw = Decimal("1")
    manager._last_price = Decimal("0.10")
    manager._max_gap = timedelta(hours=2)
    manager._async_sample(end)
    await hass.async_block_till_done()

    assert manager.year_start == next_year
    assert manager.year_energy == Decimal("0.5")
    assert manager.year_cost == Decimal("0.05")
    assert manager.day_energy == Decimal("0.5")
    assert manager.month_energy == Decimal("0.5")
    assert manager.calendar_month_energy == Decimal("0.5")
    assert manager.calendar_month_cost == Decimal("0.05")


async def test_hour_and_year_rollover_reset_totals(hass) -> None:
    entry = await _setup_entry(hass)
    manager = entry.runtime_data

    manager._hour_start = dt_util.now() - timedelta(hours=2)
    manager._hour_energy = Decimal("5")
    manager._hour_cost = Decimal("1")
    manager._year_start = dt_util.now() - timedelta(days=400)
    manager._year_energy = Decimal("5")
    manager._year_cost = Decimal("1")
    manager._ensure_periods(dt_util.now())

    assert manager.hour_energy == Decimal("0")
    assert manager.hour_cost == Decimal("0")
    assert manager.year_energy == Decimal("0")
    assert manager.year_cost == Decimal("0")


async def test_entities_link_to_power_device(hass) -> None:
    source_entry = MockConfigEntry(domain="test", title="Source", data={})
    source_entry.add_to_hass(hass)

    device = dr.async_get(hass).async_get_or_create(
        config_entry_id=source_entry.entry_id,
        identifiers={("test", "plug_device")},
        name="Plug device",
    )
    registry = er.async_get(hass)
    registry.async_get_or_create(
        "sensor",
        "test",
        "plug_power_unique",
        suggested_object_id="plug_power",
        device_id=device.id,
    )

    entry = await _setup_entry(hass)

    entities = er.async_entries_for_config_entry(registry, entry.entry_id)
    assert entities
    assert all(entity.device_id == device.id for entity in entities)


async def test_dst_fall_back_does_not_merge_hours(hass) -> None:
    await hass.config.async_set_time_zone("Europe/Madrid")
    try:
        entry = await _setup_entry(hass)
        manager = entry.runtime_data
        tz = ZoneInfo("Europe/Madrid")

        start = datetime(2027, 10, 31, 1, 30, tzinfo=tz)
        end = datetime(2027, 10, 31, 2, 30, tzinfo=tz, fold=1)

        manager._last_sample = dt_util.as_utc(start)
        manager._last_power_kw = Decimal("1")
        manager._last_price = Decimal("0.10")
        manager._max_gap = timedelta(hours=3)
        manager._async_sample(dt_util.as_utc(end))
        await hass.async_block_till_done()

        assert manager.hour_energy == Decimal("0.5")
        assert manager.last_hour_start == datetime(2027, 10, 31, 2, 0, tzinfo=tz)
        assert manager.last_hour_energy == Decimal("1.0")
        assert manager.last_hour_cost == Decimal("0.10")
        assert manager.day_energy == Decimal("2.0")
        assert manager.total_energy == Decimal("2.0")
    finally:
        await hass.config.async_set_time_zone("UTC")


async def test_invalid_power_unit_and_non_finite_price_are_ignored(hass) -> None:
    entry = await _setup_entry(hass)
    manager = entry.runtime_data

    start = dt_util.utcnow().replace(hour=12, minute=0, second=0, microsecond=0)
    start += timedelta(days=1)
    manager._last_sample = start
    manager._last_power_kw = Decimal("1")
    manager._last_price = Decimal("0.10")
    manager._max_gap = timedelta(hours=2)

    hass.states.async_set(
        "sensor.plug_power",
        "1000",
        {"unit_of_measurement": "bogus", "device_class": "power"},
    )
    manager._async_sample(start + timedelta(minutes=30))
    await hass.async_block_till_done()
    assert manager.day_energy == Decimal("0")

    hass.states.async_set(
        "sensor.plug_power",
        "1000",
        {"unit_of_measurement": "W", "device_class": "power"},
    )
    hass.states.async_set(
        DEFAULT_PRICE_ENTITY,
        "nan",
        {"unit_of_measurement": "€/kWh"},
    )
    manager._last_sample = start + timedelta(minutes=30)
    manager._last_power_kw = Decimal("1")
    manager._last_price = Decimal("0.10")
    manager._async_sample(start + timedelta(minutes=60))
    await hass.async_block_till_done()

    assert manager.status == "price_unavailable"
    assert manager.day_energy == Decimal("0")


async def test_lifetime_totals_do_not_reset_with_periods(hass) -> None:
    entry = await _setup_entry(hass)
    manager = entry.runtime_data

    start = dt_util.utcnow().replace(hour=12, minute=0, second=0, microsecond=0)
    start += timedelta(days=1)
    manager._last_sample = start
    manager._last_power_kw = Decimal("1")
    manager._last_price = Decimal("0.10")
    manager._max_gap = timedelta(hours=1)
    manager._async_sample(start + timedelta(minutes=30))
    await hass.async_block_till_done()

    assert manager.total_energy == Decimal("0.5")
    assert manager.total_cost == Decimal("0.05")

    manager._day_start = dt_util.now() - timedelta(days=1)
    manager._ensure_periods(dt_util.now())

    assert manager.day_energy == Decimal("0")
    assert manager.total_energy == Decimal("0.5")
    assert manager.total_cost == Decimal("0.05")


async def test_sensor_values_are_quantized(hass) -> None:
    entry = await _setup_entry(hass)
    manager = entry.runtime_data

    start = dt_util.start_of_local_day(
        dt_util.now() + timedelta(days=1)
    ) + timedelta(hours=12)
    end = start + timedelta(minutes=10)

    manager._last_sample = dt_util.as_utc(start)
    manager._last_power_kw = Decimal("1")
    manager._last_price = Decimal("0.10")
    manager._max_gap = timedelta(hours=1)
    manager._async_sample(dt_util.as_utc(end))
    await hass.async_block_till_done()

    registry = er.async_get(hass)
    entities = {
        entity.unique_id: entity.entity_id
        for entity in er.async_entries_for_config_entry(registry, entry.entry_id)
    }

    cost_state = hass.states.get(entities[f"{entry.entry_id}_cost_today"])
    energy_state = hass.states.get(entities[f"{entry.entry_id}_energy_today"])
    assert Decimal(cost_state.state) == Decimal("0.016667")
    assert Decimal(energy_state.state) == Decimal("0.166667")


async def test_unload_saves_state(hass) -> None:
    entry = await _setup_entry(hass)
    assert await hass.config_entries.async_unload(entry.entry_id)
    await hass.async_block_till_done()
    assert entry.state is ConfigEntryState.NOT_LOADED


async def test_shutdown_saves_latest_totals(hass) -> None:
    entry = await _setup_entry(hass)
    manager = entry.runtime_data
    assert await manager._store.async_load() is None

    start = dt_util.utcnow().replace(hour=12, minute=0, second=0, microsecond=0)
    start += timedelta(days=1)
    manager._last_sample = start
    manager._last_power_kw = Decimal("1")
    manager._last_price = Decimal("0.10")
    manager._max_gap = timedelta(hours=1)
    manager._last_save = dt_util.utcnow()
    manager._async_sample(start + timedelta(minutes=30))
    await hass.async_block_till_done()

    assert await manager._store.async_load() is None

    hass.bus.async_fire(EVENT_HOMEASSISTANT_STOP)
    await hass.async_block_till_done()

    stored = await manager._store.async_load()
    assert stored is not None
    assert Decimal(stored["hour_energy"]) == Decimal("0.5")
    assert Decimal(stored["hour_cost"]) == Decimal("0.05")
    assert Decimal(stored["day_energy"]) == Decimal("0.5")
    assert Decimal(stored["day_cost"]) == Decimal("0.05")
    assert Decimal(stored["calendar_month_energy"]) == Decimal("0.5")
    assert Decimal(stored["calendar_month_cost"]) == Decimal("0.05")
    assert Decimal(stored["last_month_energy"]) == Decimal("0")
    assert Decimal(stored["last_month_cost"]) == Decimal("0")
    assert Decimal(stored["year_energy"]) == Decimal("0.5")
    assert Decimal(stored["year_cost"]) == Decimal("0.05")
    assert Decimal(stored["total_energy"]) == Decimal("0.5")
    assert Decimal(stored["total_cost"]) == Decimal("0.05")


def test_default_price_entity_in_form() -> None:
    schema = _user_schema()
    result = schema(
        {
            CONF_NAME: "Plug",
            CONF_POWER_ENTITY: "sensor.plug_power",
            CONF_BILLING_DAY: 1,
            CONF_SCAN_INTERVAL: 60,
        }
    )
    assert result[CONF_PRICE_ENTITY] == DEFAULT_PRICE_ENTITY
    assert DEFAULT_PRICE_ENTITY == "sensor.esios_pvpc"


async def test_input_number_price_accumulation(hass) -> None:
    entry = await _setup_entry(
        hass, price_entity="input_number.tarifa", price="0.25"
    )
    manager = entry.runtime_data

    start = dt_util.utcnow().replace(hour=12, minute=0, second=0, microsecond=0)
    start += timedelta(days=1)
    manager._last_sample = start
    manager._last_power_kw = Decimal("1")
    manager._last_price = Decimal("0.25")
    manager._max_gap = timedelta(hours=1)
    manager._async_sample(start + timedelta(minutes=30))
    await hass.async_block_till_done()

    assert manager.day_energy == Decimal("0.5")
    assert manager.day_cost == Decimal("0.125")


async def test_config_flow_accepts_input_number_price(hass) -> None:
    hass.states.async_set(
        "sensor.plug_power",
        "1000",
        {"unit_of_measurement": "W", "device_class": "power"},
    )
    hass.states.async_set(
        "input_number.tarifa",
        "0.25",
        {"unit_of_measurement": "€/kWh"},
    )

    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": "user"}
    )
    assert result["type"] is FlowResultType.FORM

    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        {
            CONF_NAME: "Plug",
            CONF_POWER_ENTITY: "sensor.plug_power",
            CONF_PRICE_ENTITY: "input_number.tarifa",
            CONF_BILLING_DAY: 1,
            CONF_SCAN_INTERVAL: 60,
        },
    )

    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["data"][CONF_PRICE_ENTITY] == "input_number.tarifa"
    await hass.async_block_till_done()


async def test_config_flow(hass) -> None:
    hass.states.async_set(
        "sensor.plug_power",
        "1000",
        {"unit_of_measurement": "W", "device_class": "power"},
    )
    hass.states.async_set(
        DEFAULT_PRICE_ENTITY,
        "0.10",
        {"unit_of_measurement": "€/kWh"},
    )

    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": "user"}
    )
    assert result["type"] is FlowResultType.FORM

    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        {
            CONF_NAME: "Plug",
            CONF_POWER_ENTITY: "sensor.plug_power",
            CONF_PRICE_ENTITY: DEFAULT_PRICE_ENTITY,
            CONF_BILLING_DAY: 15,
            CONF_SCAN_INTERVAL: 120,
        },
    )

    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["title"] == "Plug"
    assert result["data"][CONF_BILLING_DAY] == 15
    await hass.async_block_till_done()


async def test_options_flow_reloads_entry(hass) -> None:
    entry = await _setup_entry(hass)

    result = await hass.config_entries.options.async_init(entry.entry_id)
    assert result["type"] is FlowResultType.FORM

    result = await hass.config_entries.options.async_configure(
        result["flow_id"],
        {
            CONF_POWER_ENTITY: "sensor.plug_power",
            CONF_PRICE_ENTITY: DEFAULT_PRICE_ENTITY,
            CONF_BILLING_DAY: 15,
            CONF_SCAN_INTERVAL: 120,
        },
    )

    assert result["type"] is FlowResultType.CREATE_ENTRY
    await hass.async_block_till_done()
    assert entry.options[CONF_BILLING_DAY] == 15
    assert entry.state is ConfigEntryState.LOADED


async def test_options_flow_rejects_duplicates_and_updates_unique_id(hass) -> None:
    entry_one = await _setup_entry(
        hass, "sensor.plug_one_power", "Plug one"
    )
    await _setup_entry(hass, "sensor.plug_two_power", "Plug two")

    result = await hass.config_entries.options.async_init(entry_one.entry_id)
    assert result["type"] is FlowResultType.FORM

    result = await hass.config_entries.options.async_configure(
        result["flow_id"],
        {
            CONF_POWER_ENTITY: "sensor.plug_two_power",
            CONF_PRICE_ENTITY: DEFAULT_PRICE_ENTITY,
            CONF_BILLING_DAY: 1,
            CONF_SCAN_INTERVAL: 60,
        },
    )
    assert result["type"] is FlowResultType.FORM
    assert result["errors"] == {"base": "already_configured"}

    hass.states.async_set(
        "sensor.plug_three_power",
        "1000",
        {"unit_of_measurement": "W", "device_class": "power"},
    )
    result = await hass.config_entries.options.async_configure(
        result["flow_id"],
        {
            CONF_POWER_ENTITY: "sensor.plug_three_power",
            CONF_PRICE_ENTITY: DEFAULT_PRICE_ENTITY,
            CONF_BILLING_DAY: 1,
            CONF_SCAN_INTERVAL: 60,
        },
    )

    assert result["type"] is FlowResultType.CREATE_ENTRY
    await hass.async_block_till_done()
    assert entry_one.unique_id == f"sensor.plug_three_power_{DEFAULT_PRICE_ENTITY}"
    assert entry_one.options[CONF_POWER_ENTITY] == "sensor.plug_three_power"
    assert entry_one.state is ConfigEntryState.LOADED


async def test_ha_event_loop_is_not_blocked(hass) -> None:
    await _setup_entry(hass)
    started = time.monotonic()
    await hass.async_block_till_done()
    assert time.monotonic() - started < 5
