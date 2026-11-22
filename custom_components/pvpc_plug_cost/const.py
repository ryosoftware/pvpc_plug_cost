"""Constants for the PVPC Plug Cost integration."""

from datetime import timedelta
from typing import Final

from homeassistant.const import (
    CURRENCY_EURO,
    Platform,
    UnitOfEnergy,
    UnitOfPower,
)

DOMAIN: Final = "pvpc_plug_cost"
NAME: Final = "PVPC Plug Cost"
VERSION: Final = "1.1.0"

CONF_POWER_ENTITY: Final = "power_entity"
CONF_PRICE_ENTITY: Final = "price_entity"
CONF_BILLING_DAY: Final = "billing_day"
CONF_SCAN_INTERVAL: Final = "scan_interval"

DEFAULT_PRICE_ENTITY: Final = "sensor.esios_pvpc"
DEFAULT_BILLING_DAY: Final = 1
DEFAULT_SCAN_INTERVAL: Final = 60
MIN_SCAN_INTERVAL: Final = 10
MAX_SCAN_INTERVAL: Final = 3600

POWER_UNITS: Final = (UnitOfPower.WATT, UnitOfPower.KILO_WATT)
PRICE_UNITS: Final = (
    f"{CURRENCY_EURO}/{UnitOfEnergy.KILO_WATT_HOUR}",
    "EUR/kWh",
)

MAX_GAP: Final = timedelta(minutes=10)
SAVE_INTERVAL: Final = timedelta(seconds=60)
STORAGE_VERSION: Final = 1

PLATFORMS: Final = [Platform.SENSOR]
