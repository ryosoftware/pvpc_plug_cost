"""Sensors for PVPC Plug Cost."""

from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass
from decimal import Decimal
from typing import Any

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorStateClass,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import (
    CURRENCY_EURO,
    UnitOfEnergy,
    UnitOfTime,
)
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .const import DOMAIN
from .manager import PVPCCostManager

STATE_QUANTUM = Decimal("0.000001")


@dataclass(frozen=True, kw_only=True)
class PVPCCostSensorDescription:
    """Description of a PVPC cost sensor."""

    key: str
    translation_key: str
    native_unit_of_measurement: str
    state_class: SensorStateClass | None
    suggested_display_precision: int
    icon: str
    value_fn: Callable[[PVPCCostManager], Decimal | None]
    device_class: SensorDeviceClass | None = None
    entity_registry_enabled_default: bool = True


SENSOR_TYPES: tuple[PVPCCostSensorDescription, ...] = (
    PVPCCostSensorDescription(
        key="cost_hour",
        translation_key="cost_hour",
        native_unit_of_measurement=CURRENCY_EURO,
        device_class=SensorDeviceClass.MONETARY,
        state_class=None,
        suggested_display_precision=4,
        icon="mdi:currency-eur",
        value_fn=lambda manager: manager.hour_cost,
    ),
    PVPCCostSensorDescription(
        key="energy_hour",
        translation_key="energy_hour",
        native_unit_of_measurement=UnitOfEnergy.KILO_WATT_HOUR,
        device_class=SensorDeviceClass.ENERGY,
        state_class=None,
        suggested_display_precision=3,
        icon="mdi:lightning-bolt",
        value_fn=lambda manager: manager.hour_energy,
    ),
    PVPCCostSensorDescription(
        key="cost_today",
        translation_key="cost_today",
        native_unit_of_measurement=CURRENCY_EURO,
        device_class=SensorDeviceClass.MONETARY,
        state_class=None,
        suggested_display_precision=4,
        icon="mdi:currency-eur",
        value_fn=lambda manager: manager.day_cost,
    ),
    PVPCCostSensorDescription(
        key="cost_month",
        translation_key="cost_month",
        native_unit_of_measurement=CURRENCY_EURO,
        device_class=SensorDeviceClass.MONETARY,
        state_class=None,
        suggested_display_precision=4,
        icon="mdi:currency-eur",
        value_fn=lambda manager: manager.month_cost,
    ),
    PVPCCostSensorDescription(
        key="energy_today",
        translation_key="energy_today",
        native_unit_of_measurement=UnitOfEnergy.KILO_WATT_HOUR,
        device_class=SensorDeviceClass.ENERGY,
        state_class=None,
        suggested_display_precision=3,
        icon="mdi:lightning-bolt",
        value_fn=lambda manager: manager.day_energy,
    ),
    PVPCCostSensorDescription(
        key="energy_month",
        translation_key="energy_month",
        native_unit_of_measurement=UnitOfEnergy.KILO_WATT_HOUR,
        device_class=SensorDeviceClass.ENERGY,
        state_class=None,
        suggested_display_precision=3,
        icon="mdi:lightning-bolt",
        value_fn=lambda manager: manager.month_energy,
    ),
    PVPCCostSensorDescription(
        key="cost_year",
        translation_key="cost_year",
        native_unit_of_measurement=CURRENCY_EURO,
        device_class=SensorDeviceClass.MONETARY,
        state_class=None,
        suggested_display_precision=4,
        icon="mdi:currency-eur",
        value_fn=lambda manager: manager.year_cost,
    ),
    PVPCCostSensorDescription(
        key="energy_year",
        translation_key="energy_year",
        native_unit_of_measurement=UnitOfEnergy.KILO_WATT_HOUR,
        device_class=SensorDeviceClass.ENERGY,
        state_class=None,
        suggested_display_precision=3,
        icon="mdi:lightning-bolt",
        value_fn=lambda manager: manager.year_energy,
    ),
    PVPCCostSensorDescription(
        key="energy_total",
        translation_key="energy_total",
        native_unit_of_measurement=UnitOfEnergy.KILO_WATT_HOUR,
        device_class=SensorDeviceClass.ENERGY,
        state_class=SensorStateClass.TOTAL_INCREASING,
        suggested_display_precision=3,
        icon="mdi:lightning-bolt",
        value_fn=lambda manager: manager.total_energy,
    ),
    PVPCCostSensorDescription(
        key="cost_total",
        translation_key="cost_total",
        native_unit_of_measurement=CURRENCY_EURO,
        device_class=SensorDeviceClass.MONETARY,
        state_class=SensorStateClass.TOTAL,
        suggested_display_precision=4,
        icon="mdi:currency-eur",
        value_fn=lambda manager: manager.total_cost,
    ),
    PVPCCostSensorDescription(
        key="cost_rate",
        translation_key="cost_rate",
        native_unit_of_measurement=f"{CURRENCY_EURO}/{UnitOfTime.HOURS}",
        state_class=SensorStateClass.MEASUREMENT,
        suggested_display_precision=4,
        icon="mdi:cash-clock",
        value_fn=lambda manager: manager.current_cost_rate,
        entity_registry_enabled_default=False,
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up the cost sensors for a config entry."""

    manager: PVPCCostManager = entry.runtime_data
    async_add_entities(
        PVPCCostSensor(manager, description) for description in SENSOR_TYPES
    )


class PVPCCostSensor(SensorEntity):
    """Representation of one PVPC cost or energy sensor."""

    _attr_has_entity_name = True
    _attr_should_poll = False

    def __init__(
        self,
        manager: PVPCCostManager,
        description: PVPCCostSensorDescription,
    ) -> None:
        self._manager = manager
        self._description = description
        self._attr_unique_id = f"{manager.entry.entry_id}_{description.key}"
        self._attr_translation_key = description.translation_key
        self._attr_native_unit_of_measurement = (
            description.native_unit_of_measurement
        )
        self._attr_device_class = description.device_class
        self._attr_state_class = description.state_class
        self._attr_suggested_display_precision = (
            description.suggested_display_precision
        )
        self._attr_icon = description.icon
        self._attr_entity_registry_enabled_default = (
            description.entity_registry_enabled_default
        )

        if manager.device_entry is not None:
            self.device_entry = manager.device_entry
        else:
            self._attr_device_info = DeviceInfo(
                identifiers={(DOMAIN, manager.entry.entry_id)},
                name=manager.entry.title,
                manufacturer="PVPC Plug Cost",
                model="PVPC cost tracker",
            )

    async def async_added_to_hass(self) -> None:
        """Subscribe to manager updates."""

        await super().async_added_to_hass()
        self.async_on_remove(
            self._manager.async_add_listener(self.async_write_ha_state)
        )

    @property
    def native_value(self) -> Decimal | None:
        """Return the current sensor value."""

        return _quantize(self._description.value_fn(self._manager))

    @property
    def extra_state_attributes(self) -> Mapping[str, Any]:
        """Return diagnostic attributes."""

        manager = self._manager
        return {
            "source_power_entity": manager.power_entity,
            "source_price_entity": manager.price_entity,
            "current_power_kw": _as_float(manager.current_power_kw),
            "current_price_eur_kwh": _as_float(manager.current_price),
            "current_cost_rate_eur_h": _as_float(manager.current_cost_rate),
            "billing_day": manager.billing_day,
            "status": manager.status,
            "last_sample": (
                manager.last_sample.isoformat() if manager.last_sample else None
            ),
        }


def _quantize(value: Decimal | None) -> Decimal | None:
    if value is None:
        return None
    return value.quantize(STATE_QUANTUM)


def _as_float(value: Decimal | None) -> float | None:
    if value is None:
        return None
    return round(float(value), 6)
