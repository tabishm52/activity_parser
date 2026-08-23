# activity-parser

[![CI](https://github.com/tabishm52/activity_parser/actions/workflows/ci.yml/badge.svg?branch=main)](https://github.com/tabishm52/activity_parser/actions/workflows/ci.yml)
[![PyPI](https://img.shields.io/pypi/v/activity-parser)](https://pypi.org/project/activity-parser/)
[![Python versions](https://img.shields.io/pypi/pyversions/activity-parser)](https://pypi.org/project/activity-parser/)
[![License](https://img.shields.io/pypi/l/activity-parser)](https://pypi.org/project/activity-parser/)

Parser for loading FIT, TCX and GPX activity files into Pandas DataFrames.

Provides a parser object for reading (optionally gzipped) FIT, TCX, and GPX activity files and converting them into Pandas DataFrames.
During import, field names extracted from activity files are normalized into a canonical set of output column names with consistent units to allow for standardized downstream data processing.

## Installation

```bash
pip install activity-parser
```

## Usage

Create a new instance of the `ActivityParser` class to be reused for subsequent parsing of activity files:

```python
import activity_parser

parser = activity_parser.ActivityParser()
```

Parse FIT, TCX and GPX files into normalized DataFrames:

```python
records, laps, activity = parser.parse("path/to/fit_file.fit")
records, laps, activity = parser.parse("path/to/gpx_file.gpx")
records, laps, activity = parser.parse("path/to/tcx_file.tcx")
```

Each file is assumed to contain a single activity.
Multiple activities/tracks (chained FIT files, multi-activity TCX, multi-track GPX) have their records/laps merged into one set of results.
In those cases, the returned `Activity` summary reflects only the first activity/session in the file.

## Output data

`records` and `laps` are each a DataFrame of normalized data, e.g.:

```
                           distance  speed  cadence  heart_rate
time
2026-01-05 08:00:00+00:00      0.00   36.0       80         100
2026-01-05 08:00:01+00:00      0.01   36.0       81         101
```

A few notes on column handling:

- Column names and units are standardized across source formats for known field types.
- Unknown fields are omitted by default; customize columns via `record_columns`, `lap_columns`, and `include_all_columns` on `ActivityParser` — see its docstring for details.
- Not every column appears in every file: `parse()` only includes columns actually present.

### Records

Not all fields are available in all source formats.
Fields marked with (\*) are exporter-dependent.

| Column | Unit | FIT | TCX | GPX |
|---|---|:-:|:-:|:-:|
| `latitude`, `longitude` | degrees | Yes | Yes | Yes |
| `altitude` | meters | Yes | Yes | Yes |
| `distance` | km | Yes | Yes | (\*) |
| `speed` | km/h | Yes | (\*) | (\*) |
| `cadence` | rpm | Yes | Yes | (\*) |
| `heart_rate` | bpm | Yes | Yes | (\*) |
| `power` | watts | Yes | (\*) | (\*) |
| `left_balance`, `right_balance` | percent | Yes | — | — |
| `accumulated_power` | watts | Yes | — | — |
| `temperature` | °C | Yes | — | (\*) |
| `water_temperature` | °C | — | — | (\*) |
| `depth` | meters | — | — | (\*) |
| `course`, `bearing` | degrees | — | — | (\*) |

### Laps

GPX files have no lap data, so `laps` is always an empty DataFrame for GPX.
Fields marked with (\*) are exporter-dependent.

| Column | Unit | FIT | TCX |
|---|---|:-:|:-:|
| `start_time` | timestamp | Yes | Yes |
| `total_elapsed_time` | seconds | Yes | Yes |
| `total_timer_time` | seconds | Yes | — |
| `start_position_lat`, `start_position_long` | degrees | Yes | — |
| `end_position_lat`, `end_position_long` | degrees | Yes | — |
| `total_distance` | km | Yes | Yes |
| `total_ascent`, `total_descent` | meters | Yes | — |
| `avg_vam` | m/s | Yes | — |
| `avg_speed` | km/h | Yes | (\*) |
| `max_speed` | km/h | Yes | Yes |
| `avg_cadence` | rpm | Yes | Yes |
| `max_cadence` | rpm | Yes | (\*) |
| `total_strokes` | count | Yes | — |
| `steps` | count | — | (\*) |
| `avg_heart_rate`, `max_heart_rate` | bpm | Yes | Yes |
| `time_in_hr_zone` | seconds | Yes | — |
| `avg_power`, `max_power` | watts | Yes | (\*) |
| `normalized_power` | watts | Yes | — |
| `left_balance`, `right_balance` | percent | Yes | — |
| `time_in_power_zone` | seconds | Yes | — |
| `total_work` | joules | Yes | — |
| `avg_temperature`, `max_temperature` | °C | Yes | — |
| `total_calories` | kcal | Yes | Yes |
| `total_fat_calories` | kcal | Yes | — |

### Activity

`activity` is an `Activity` dataclass instance: a small file-level summary.
Fields are `None` when the source format/file doesn't record them.
Values come from the file's own summary fields, never computed/derived from records or laps.

| Field | Unit | FIT | TCX | GPX |
|---|---|:-:|:-:|:-:|
| `sport` | — | Yes | Yes | — |
| `start_time` | — | Yes | Yes | Yes (\*) |
| `total_elapsed_time` | seconds | Yes | — | — |
| `total_distance` | km | Yes | — | — |
| `total_calories` | kcal | Yes | — | — |
| `avg_heart_rate`, `max_heart_rate` | bpm | Yes | — | — |
| `avg_speed`, `max_speed` | km/h | Yes | — | — |
| `creator` | — | Yes | Yes | Yes |
| `notes` | — | — | Yes | Yes |

(\*) GPX's `start_time` comes from `metadata/time`, which is technically the file's export time rather than the activity's start.

## Parser notes

### FIT files

FIT parsing wraps [`garmin-fit-sdk`](https://pypi.org/project/garmin-fit-sdk/), Garmin's official SDK, which decodes against the public FIT SDK profile.

`parse()` transforms certain FIT fields beyond decoding:

- Positions are converted to degrees, distances to km, and speeds to km/h.
  Vertical rates (`avg_vam`, `vertical_speed`, and similar) stay in m/s.
- For fields with lower- and higher-precision versions, only the higher-precision value is returned, under the base field's name.
- For fields with sub-integer precision in a separate field, the precision is added into the base field.
- `left_right_balance` (a bit-packed field) is decoded into `left_balance`/`right_balance`.
- `heart_rate` is merged with a higher-rate `hr` stream when the file has one.
  Records outside its coverage keep their own device value.

Messages/fields that can't be resolved against the FIT profile (e.g. proprietary extensions) are kept as raw values under `unknown_<n>` names.
Developer fields are resolved to their file-embedded names and flattened into ordinary columns alongside built-in fields.

### TCX & GPX files

TCX and GPX files are parsed natively in this package using [`lxml`](https://pypi.org/project/lxml/).
Recognized elements and attributes are mapped onto the same canonical column names as FIT, with the same unit conventions.

The parser supports the following schema versions and extensions:

| Format | Schema version | Extensions |
|---|---|---|
| TCX | v2 | Garmin `ActivityExtension` v2 |
| GPX | 1.0 / 1.1 | Garmin `TrackPointExtension` v1/v2, Cluetrust `gpxdata` |

Unrecognized elements and attributes are exported as string columns named with their XML namespace in Clark notation.
