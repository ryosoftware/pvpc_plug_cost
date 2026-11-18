"""The PVPC Plug Cost integration."""

from __future__ import annotations

from datetime import timedelta

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.storage import Store

from .const import (
    CONF_BILLING_DAY,
    CONF_POWER_ENTITY,
    CONF_PRICE_ENTITY,
    CONF_SCAN_INTERVAL,
    DOMAIN,
    PLATFORMS,
    STORAGE_VERSION,
)
from .manager import PVPCCostManager


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up PVPC Plug Cost from a config entry."""

    config = {**entry.data, **entry.options}
    manager = PVPCCostManager(
        hass=hass,
        entry=entry,
        power_entity=config[CONF_POWER_ENTITY],
        price_entity=config[CONF_PRICE_ENTITY],
        billing_day=int(config[CONF_BILLING_DAY]),
        scan_interval=timedelta(seconds=int(config[CONF_SCAN_INTERVAL])),
    )

    await manager.async_load()
    await manager.async_start()
    entry.runtime_data = manager

    try:
        await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    except Exception:
        await manager.async_stop()
        raise
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""

    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unload_ok:
        await entry.runtime_data.async_stop()
    return unload_ok


async def async_remove_entry(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Remove persisted data when a config entry is deleted."""

    store = Store(hass, STORAGE_VERSION, f"{DOMAIN}.{entry.entry_id}")
    await store.async_remove()
