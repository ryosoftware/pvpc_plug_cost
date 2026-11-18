"""Config flow for PVPC Plug Cost."""

from __future__ import annotations

from typing import Any

import voluptuous as vol

from homeassistant import config_entries
from homeassistant.components.sensor import SensorDeviceClass
from homeassistant.config_entries import ConfigFlowResult, OptionsFlowWithReload
from homeassistant.const import ATTR_UNIT_OF_MEASUREMENT, CONF_NAME
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers import selector

from .const import (
    CONF_BILLING_DAY,
    CONF_POWER_ENTITY,
    CONF_PRICE_ENTITY,
    CONF_SCAN_INTERVAL,
    DEFAULT_BILLING_DAY,
    DEFAULT_PRICE_ENTITY,
    DEFAULT_SCAN_INTERVAL,
    DOMAIN,
    MAX_SCAN_INTERVAL,
    MIN_SCAN_INTERVAL,
    NAME,
    POWER_UNITS,
    PRICE_UNITS,
)


def _power_selector() -> selector.EntitySelector:
    return selector.EntitySelector(
        selector.EntitySelectorConfig(
            domain="sensor",
            device_class=SensorDeviceClass.POWER,
        )
    )


def _price_selector() -> selector.EntitySelector:
    return selector.EntitySelector(
        selector.EntitySelectorConfig(
            domain=["sensor", "input_number"],
        )
    )


def _billing_day_selector() -> selector.NumberSelector:
    return selector.NumberSelector(
        selector.NumberSelectorConfig(
            min=1,
            max=31,
            step=1,
            mode=selector.NumberSelectorMode.BOX,
        )
    )


def _scan_interval_selector() -> selector.NumberSelector:
    return selector.NumberSelector(
        selector.NumberSelectorConfig(
            min=MIN_SCAN_INTERVAL,
            max=MAX_SCAN_INTERVAL,
            step=1,
            unit_of_measurement="s",
            mode=selector.NumberSelectorMode.BOX,
        )
    )


def _validate_power_entity(hass: HomeAssistant, entity_id: str) -> str | None:
    state = hass.states.get(entity_id)
    if state is None:
        return "entity_not_found"
    if state.attributes.get(ATTR_UNIT_OF_MEASUREMENT) not in POWER_UNITS:
        return "invalid_power_unit"
    return None


def _validate_price_entity(hass: HomeAssistant, entity_id: str) -> str | None:
    state = hass.states.get(entity_id)
    if state is None:
        return "entity_not_found"
    if state.attributes.get(ATTR_UNIT_OF_MEASUREMENT) not in PRICE_UNITS:
        return "invalid_price_unit"
    return None


def _validate_input(hass: HomeAssistant, values: dict[str, Any]) -> dict[str, str]:
    errors: dict[str, str] = {}

    power_entity = values.get(CONF_POWER_ENTITY)
    if not isinstance(power_entity, str):
        errors[CONF_POWER_ENTITY] = "entity_not_found"
    elif error := _validate_power_entity(hass, power_entity):
        errors[CONF_POWER_ENTITY] = error

    price_entity = values.get(CONF_PRICE_ENTITY)
    if not isinstance(price_entity, str):
        errors[CONF_PRICE_ENTITY] = "entity_not_found"
    elif error := _validate_price_entity(hass, price_entity):
        errors[CONF_PRICE_ENTITY] = error

    return errors


def _required_entity(
    key: str, value: str | None, entity_selector: selector.EntitySelector
) -> dict[Any, Any]:
    if value is None:
        return {vol.Required(key): entity_selector}
    return {vol.Required(key, default=value): entity_selector}


def _user_schema(values: dict[str, Any] | None = None) -> vol.Schema:
    current = values or {}
    return vol.Schema(
        {
            vol.Required(
                CONF_NAME, default=current.get(CONF_NAME, NAME)
            ): selector.TextSelector(),
            **_required_entity(
                CONF_POWER_ENTITY,
                current.get(CONF_POWER_ENTITY),
                _power_selector(),
            ),
            **_required_entity(
                CONF_PRICE_ENTITY,
                current.get(CONF_PRICE_ENTITY, DEFAULT_PRICE_ENTITY),
                _price_selector(),
            ),
            vol.Required(
                CONF_BILLING_DAY,
                default=current.get(CONF_BILLING_DAY, DEFAULT_BILLING_DAY),
            ): _billing_day_selector(),
            vol.Required(
                CONF_SCAN_INTERVAL,
                default=current.get(CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL),
            ): _scan_interval_selector(),
        }
    )


def _options_schema(values: dict[str, Any] | None = None) -> vol.Schema:
    current = values or {}
    return vol.Schema(
        {
            **_required_entity(
                CONF_POWER_ENTITY,
                current.get(CONF_POWER_ENTITY),
                _power_selector(),
            ),
            **_required_entity(
                CONF_PRICE_ENTITY,
                current.get(CONF_PRICE_ENTITY, DEFAULT_PRICE_ENTITY),
                _price_selector(),
            ),
            vol.Required(
                CONF_BILLING_DAY,
                default=current.get(CONF_BILLING_DAY, DEFAULT_BILLING_DAY),
            ): _billing_day_selector(),
            vol.Required(
                CONF_SCAN_INTERVAL,
                default=current.get(CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL),
            ): _scan_interval_selector(),
        }
    )


def _entry_data(values: dict[str, Any]) -> dict[str, Any]:
    return {
        CONF_POWER_ENTITY: values[CONF_POWER_ENTITY],
        CONF_PRICE_ENTITY: values[CONF_PRICE_ENTITY],
        CONF_BILLING_DAY: int(values[CONF_BILLING_DAY]),
        CONF_SCAN_INTERVAL: int(values[CONF_SCAN_INTERVAL]),
    }


class PVPCCostConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle the initial configuration."""

    VERSION = 1

    @staticmethod
    @callback
    def async_get_options_flow(
        config_entry: config_entries.ConfigEntry,
    ) -> PVPCCostOptionsFlow:
        return PVPCCostOptionsFlow()

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        errors: dict[str, str] = {}

        if user_input is not None:
            errors = _validate_input(self.hass, user_input)

            if not errors:
                name = str(user_input[CONF_NAME]).strip() or NAME
                await self.async_set_unique_id(
                    f"{user_input[CONF_POWER_ENTITY]}_{user_input[CONF_PRICE_ENTITY]}"
                )
                self._abort_if_unique_id_configured()
                return self.async_create_entry(
                    title=name,
                    data=_entry_data(user_input),
                )

        return self.async_show_form(
            step_id="user",
            data_schema=_user_schema(user_input),
            errors=errors,
        )


class PVPCCostOptionsFlow(OptionsFlowWithReload):
    """Handle options updates."""

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        errors: dict[str, str] = {}
        current = {**self.config_entry.data, **self.config_entry.options}

        if user_input is not None:
            errors = _validate_input(self.hass, user_input)

            if not errors:
                unique_id = (
                    f"{user_input[CONF_POWER_ENTITY]}_"
                    f"{user_input[CONF_PRICE_ENTITY]}"
                )
                if any(
                    entry.entry_id != self.config_entry.entry_id
                    and entry.unique_id == unique_id
                    for entry in self.hass.config_entries.async_entries(DOMAIN)
                ):
                    errors["base"] = "already_configured"
                else:
                    if self.config_entry.unique_id != unique_id:
                        self.hass.config_entries.async_update_entry(
                            self.config_entry, unique_id=unique_id
                        )
                    return self.async_create_entry(
                        title="",
                        data=_entry_data(user_input),
                    )

        return self.async_show_form(
            step_id="init",
            data_schema=_options_schema(user_input or current),
            errors=errors,
        )
