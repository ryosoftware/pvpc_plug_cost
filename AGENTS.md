# AGENTS.md

## Project

Home Assistant custom integration `pvpc_plug_cost` for HACS. It calculates the variable PVPC energy cost of one or more smart plugs that expose only a power sensor in `W` or `kW`.

- Domain: `pvpc_plug_cost`
- Minimum Home Assistant version: `2025.8.0`
- Tested with Home Assistant `2026.2.3`
- No runtime Python requirements (`manifest.json` has `"requirements": []`)
- Requires the official PVPC Hourly Pricing integration and a power sensor in `W` or `kW`
- The price is read from an entity; `pvpc_hourly_pricing` is listed in `after_dependencies`, not as a hard dependency, because fixed tariffs can use an `input_number`
- One config entry per plug; no global aggregate sensor
- Cost is variable energy cost only: no taxes, tolls, contracted power or meter rental

## Repository layout

```text
custom_components/pvpc_plug_cost/
├── __init__.py          # setup, unload, removal, Store cleanup
├── brand/               # icon.png, icon@2x.png
├── calculator.py        # pure math, no Home Assistant imports
├── config_flow.py       # user and options flows
├── const.py             # constants, units, defaults
├── manager.py           # sampling engine and persistence
├── manifest.json
├── sensor.py            # cost and energy entities
├── strings.json
└── translations/        # en.json, es.json
.github/workflows/
└── validate.yaml        # HACS validation action
tests/
├── conftest.py
├── test_calculator.py
└── test_integration.py
hacs.json
pytest.ini
requirements-dev.txt
README.md
```

## Architecture

### `calculator.py`

Pure calculation module with no Home Assistant imports. Keep it this way so it can be tested without Home Assistant.

- `accumulate_segment()` integrates power over a time segment using the trapezoidal rule and multiplies by the price.
- `billing_period_start()` and `next_billing_period_start()` implement the configurable billing day.
- Billing days 29–31 are clamped to the last day of the month.
- `period_boundaries()` returns day and billing-period boundaries that must split an accumulation interval.

### `manager.py`

One `PVPCCostManager` instance per config entry.

- Reads power and price states.
- Converts power to kW with `PowerConverter`.
- Samples on power/price state changes, every configured interval, and every hour.
- Uses UTC for elapsed-time math and local time for hour, day, month and year boundaries. Hour boundaries support whole-hour and half-hour offsets and DST folds. Period-start comparisons are converted to UTC so DST folds are handled correctly.
- Stores `hour_*`, `last_hour_*`, `day_*`, `month_*`, `year_*` and `total_*` totals plus period starts.
- `last_hour_*` is promoted only when the hour rollover is observed while running; it is persisted and restored but hours spanning downtime are not reconstructed.
- Lifetime `total_*` counters never reset and are intended for the Energy Dashboard; period counters remain informative.
- Persists state with `Store` under `pvpc_plug_cost.<entry_id>`.
- Saves at most once per minute while accumulating and always on Home Assistant shutdown (`EVENT_HOMEASSISTANT_STOP`). Writes are serialized with a lock so the final save cannot be overwritten by an older periodic save.
- Does not count time while Home Assistant is down.
- Stops accumulating when power or price is unavailable and resumes without counting the gap.
- `MAX_GAP` is at least 10 minutes or three times the configured scan interval.

### `sensor.py`

Thirteen entities:

| Key | Unit | Device class | State class | Icon |
|---|---|---|---|---|
| `cost_hour` | € | `monetary` | none | `mdi:currency-eur` |
| `energy_hour` | kWh | `energy` | none | `mdi:lightning-bolt` |
| `cost_last_hour` | € | `monetary` | none | `mdi:currency-eur` |
| `energy_last_hour` | kWh | `energy` | none | `mdi:lightning-bolt` |
| `cost_today` | € | `monetary` | none | `mdi:currency-eur` |
| `cost_month` | € | `monetary` | none | `mdi:currency-eur` |
| `energy_today` | kWh | `energy` | none | `mdi:lightning-bolt` |
| `energy_month` | kWh | `energy` | none | `mdi:lightning-bolt` |
| `cost_year` | € | `monetary` | none | `mdi:currency-eur` |
| `energy_year` | kWh | `energy` | none | `mdi:lightning-bolt` |
| `energy_total` | kWh | `energy` | `total_increasing` | `mdi:lightning-bolt` |
| `cost_total` | € | `monetary` | `total` | `mdi:currency-eur` |
| `cost_rate` | €/h | none | `measurement` | `mdi:cash-clock` |

`cost_rate` is disabled by default.

Entity IDs use the language-independent description key (`cost_hour`, `cost_today`, etc.) via `suggested_object_id`, so new installations get the same entity IDs regardless of the Home Assistant language. Friendly names remain translated. Existing entity IDs are not migrated.

`cost_last_hour` and `energy_last_hour` show the previous clock hour (for example, at 10:25 the 09:00–10:00 period). They advance only when the rollover is observed while running; they are persisted and restored but do not reconstruct hours spanning downtime.

Important: invalid Material Design Icons names render as no icon. Do not use `mdi:calendar-currency` or `mdi:calendar-lightning`; they do not exist. Verify new icon names before using them.

Period sensors are informational: they have no `state_class` or `last_reset`, so they do not generate long-term statistics. Lifetime sensors do not reset; `energy_total` uses `total_increasing` and `cost_total` uses `total` because HA does not allow `monetary` with `total_increasing`. The Energy Dashboard should use `energy_total` and `cost_total`.

### `config_flow.py`

- Power selector filters by `device_class: power`.
- Price selector lists `sensor` and `input_number` entities; validation requires the unit to be `€/kWh` or `EUR/kWh`. This supports both PVPC sensors and fixed tariffs stored in an `input_number` helper.
- Default price entity is `sensor.esios_pvpc`, the entity created by the official PVPC Hourly Pricing integration.
- HA 2026.2.3 does not support `unit_of_measurement` filters inside `EntitySelectorConfig(filter=...)`; do not reintroduce that filter unless compatibility is checked.
- `unique_id` is `<power_entity>_<price_entity>`, allowing multiple plugs while preventing duplicate entries for the same pair.
- The options flow validates duplicates and updates the entry `unique_id` when the source entities change. Changing the billing day resets the current billing-period totals and this is documented in the form.
- Options use `OptionsFlowWithReload`.

### `__init__.py`

- Creates the manager, loads persisted state, starts sampling, and forwards the sensor platform.
- Stops the manager on unload and removes its `Store` when the config entry is deleted.

## Commands

Set up the development environment:

```bash
python3 -m venv .venv
.venv/bin/pip install -r requirements-dev.txt
```

Run all tests:

```bash
.venv/bin/python -m pytest -q
```

Run only the pure calculator tests without Home Assistant:

```bash
python3 -m unittest discover -s tests -v
```

Validate syntax and JSON:

```bash
python3 -m compileall -q custom_components tests
python3 -m json.tool custom_components/pvpc_plug_cost/manifest.json > /dev/null
python3 -m json.tool hacs.json > /dev/null
```

Clean generated caches:

```bash
rm -rf .pytest_cache custom_components/pvpc_plug_cost/__pycache__ tests/__pycache__
```

## Development conventions

- Target Python 3.13 and modern Home Assistant APIs.
- Use `from __future__ import annotations` in Python modules.
- Use `Decimal` for financial and energy calculations.
- Keep `calculator.py` free of Home Assistant imports.
- Use `@callback` for event-loop callbacks.
- Follow the existing docstring style; avoid unnecessary inline comments.
- Do not add a global aggregate cost sensor unless explicitly requested.
- Preserve the one-entry-per-plug design and the per-entry `Store` key.
- Integration tests may manipulate private manager attributes to simulate time; keep timestamps deterministic and in the future relative to setup.
- Do not commit `.venv`, `__pycache__` or `.pytest_cache`.

## Publishing to HACS

The repository is published at `https://github.com/ryosoftware/pvpc_plug_cost`.

Keep these fields in `custom_components/pvpc_plug_cost/manifest.json` pointing there:

- `documentation`
- `issue_tracker`
- `codeowners`

HACS installs from the repository root; only `custom_components/pvpc_plug_cost` is the integration.

## Manual installation / Docker notes

Copy only the integration folder:

```text
/custom_components/pvpc_plug_cost/
```

Do not copy `tests`, `hacs.json`, `README.md`, `LICENSE` or development files into Home Assistant.

In Docker, `docker restart` and Home Assistant restarts keep copied files. Files copied into the container writable layer are lost if the container is recreated. Use a bind mount or named volume for `/config` to persist them. Never copy the parent folder and produce `.../pvpc_plug_cost/pvpc_plug_cost/`.

After copying or editing Python files, restart Home Assistant or reload the integration. Icon and frontend changes may also require a hard browser refresh.
