# PVPC Plug Cost

English | [Español](README.md)

Custom integration for Home Assistant that calculates the variable energy cost of the energy consumed by a smart plug using the hourly PVPC price in Spain.

For each plug, it creates cost and energy sensors with daily and billing-period totals.

## Features

- One integration entry per plug; add as many as you want.
- Independent sensors per plug, grouped under the plug's device.
- Daily cost and billing-period cost.
- Daily energy and billing-period energy (kWh).
- Configurable billing day, automatically adjusted for 28, 29, 30 or 31-day months.
- Optional instantaneous cost sensor in €/h, disabled by default.
- Totals persist across Home Assistant restarts, with periodic saves (at most once per minute) and on shutdown.
- Compatible with long-term statistics and the Energy Dashboard.

## Requirements

- Home Assistant `2025.8.0` or later.
- For the PVPC tariff, the official [PVPC Hourly Pricing](https://www.home-assistant.io/integrations/pvpc_hourly_pricing/) integration configured, normally with the `sensor.esios_pvpc` sensor.
- A smart plug exposing a power sensor in W or kW.

## Price source

The integration does not query ESIOS directly. It reads the current price from the sensor created by the official [PVPC Hourly Pricing](https://www.home-assistant.io/integrations/pvpc_hourly_pricing/) integration, normally `sensor.esios_pvpc`.

For a fixed tariff, you can use an `input_number` with unit `€/kWh`; in that case the official integration does not need to be configured.

## HACS installation

1. In HACS, open **Integrations** and add `https://github.com/ryosoftware/pvpc_plug_cost` as a custom repository.
2. Select the **Integration** category.
3. Install **PVPC Plug Cost** and restart Home Assistant.

## Manual installation

Copy the `custom_components/pvpc_plug_cost` folder into the `custom_components` folder of your Home Assistant configuration and restart.

```text
/config/custom_components/pvpc_plug_cost/
```

## Configuration

1. Go to **Settings → Devices & services → Add integration**.
2. Search for **PVPC Plug Cost**.
3. Enter:
   - Name, for example `Washing machine`.
   - Power sensor of the plug, in W or kW.
   - PVPC price sensor, for example `sensor.esios_pvpc`. An `input_number` with unit `€/kWh` is also accepted for a fixed tariff.
   - Billing day, from 1 to 31.
   - Sampling interval, 60 seconds by default.
4. Repeat the process for each additional plug.

The billing day determines when the monthly counter resets. If you choose a day that does not exist in a given month, the last day of that month is used.

### Fixed tariff

If you do not use PVPC, create an `input_number` helper with the tariff in `€/kWh` and select it as the price entity. The integration validates the unit and uses its current value to calculate the cost.

## Created entities

For an entry named `Washing machine`:

| Entity | Description |
|---|---|
| `sensor.washing_machine_cost_current_hour` | Variable cost accumulated in the current hour |
| `sensor.washing_machine_energy_current_hour` | Energy accumulated in the current hour |
| `sensor.washing_machine_cost_last_hour` | Variable cost for the last complete hour |
| `sensor.washing_machine_energy_last_hour` | Energy for the last complete hour |
| `sensor.washing_machine_cost_today` | Variable cost accumulated today |
| `sensor.washing_machine_cost_current_billing_period` | Variable cost for the billing period |
| `sensor.washing_machine_energy_today` | Energy accumulated today |
| `sensor.washing_machine_energy_current_billing_period` | Energy for the billing period |
| `sensor.washing_machine_cost_current_year` | Variable cost accumulated in the current year |
| `sensor.washing_machine_energy_current_year` | Energy accumulated in the current year |
| `sensor.washing_machine_energy_total` | Total energy accumulated since installation |
| `sensor.washing_machine_cost_total` | Total variable cost accumulated since installation |
| `sensor.washing_machine_cost_rate` | Instantaneous cost in €/h, disabled by default |

The prefix depends on the device name. Entity IDs use English keys (`cost_current_hour`, `energy_total`, etc.) so they are stable and independent of the Home Assistant language; display names are still translated.

`cost_last_hour` and `energy_last_hour` show the previous clock hour: at 10:25, the 09:00–10:00 period. They only advance when Home Assistant observes the hour change while running; if it was stopped when the hour changed, they keep the last hour that was completed while running. The `last_hour_start` attribute indicates the start of the displayed period.

Each sensor includes diagnostic attributes: power entity, price entity, current power, current price, instantaneous cost, billing day, status, last sample and start of the last complete hour.

## Energy Dashboard

The recommended sensors for the Dashboard are `energy_total` and `cost_total`, because they are monotonic totals and do not reset. The energy and cost sensors for the current hour, last hour, day, billing period and year are informational and do not generate long-term statistics.

## Calculation

For each interval between samples:

```text
energy = power at start of segment (kW) × time (h)
cost   = energy (kWh) × price at start of segment (€/kWh)
```

Power and price are treated as step signals: the last known value at the start of each segment is used and held until the next reading. Intervals are split at hour changes, midnight and billing-period starts so that energy and cost are assigned correctly to each counter. Each subsegment uses the power and price from the start of the sampling interval.

Totals start counting from the moment the integration is configured. Consumption before installation is not reconstructed.

## Limitations

- The calculated cost is **only the PVPC variable energy term**. It does not include taxes, tolls, capacity charges, meter rental or other fixed charges.
- Accuracy depends on how often the plug updates power and on the sampling interval.
- Power and price are held until the next reading; they are not interpolated. If the plug or price changes with little detail, the cost may drift slightly, at most about one sampling interval per change.
- Consumption that occurred while Home Assistant or the plug was disconnected is not recovered.
- No aggregate total sensor for multiple plugs is created. If you need one, you can create a template sensor that sums the individual cost sensors.

## Development and testing

Pure calculation tests do not need Home Assistant:

```bash
python3 -m unittest discover -s tests -v
```

Integration tests use the official Home Assistant test harness:

```bash
python3 -m venv .venv
.venv/bin/pip install -r requirements-dev.txt
.venv/bin/python -m pytest
```

Basic syntax validation:

```bash
python3 -m compileall custom_components
```

## License

MIT.

## Home Assistant one-click repository link

https://my.home-assistant.io/redirect/marketplace_repository/?owner=ryosoftware&repository=https%3A%2F%2Fgithub.com%2Fryosoftware%2Fpvpc_plug_cost&category=integration
