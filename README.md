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
records, laps, activity = parser.parse('path/to/fit_file.fit')
records, laps, activity = parser.parse('path/to/gpx_file.gpx')
records, laps, activity = parser.parse('path/to/tcx_file.tcx')
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
- Unknown fields are omitted by default; customize this (or which columns are selected) via `record_columns`/`lap_columns`/`include_all_columns` on `ActivityParser` — see its docstring for details.
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
| `temperature` | °C | Yes | — | (\*) |
| `left_balance`, `right_balance` | percent | Yes | — | — |
| `accumulated_power` | watts | Yes | — | — |
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
Values are transcribed from the file, never computed/derived from records or laps.

| Field | Unit | FIT | TCX | GPX |
|---|---|:-:|:-:|:-:|
| `sport` | — | Yes | Yes | — |
| `start_time` | — | Yes | Yes | Yes (\*) |
| `total_elapsed_time` | seconds | Yes | — | — |
| `total_distance` | km | Yes | — | — |
| `total_calories` | kcal | Yes | — | — |
| `avg_heart_rate`, `max_heart_rate` | bpm | Yes | — | — |
| `avg_speed`, `max_speed` | kph | Yes | — | — |
| `creator` | — | Yes | Yes | Yes |
| `notes` | — | — | Yes | Yes |

(\*) GPX's `start_time` comes from `metadata/time`, which is technically the file's export time rather than the activity's start.

## Source format notes

### FIT files

FIT parsing wraps [`fitdecode`](https://github.com/polyvertex/fitdecode), which decodes against Garmin's public FIT SDK profile.
Field values and types come from that profile, and units are converted via fitdecode's `StandardUnitsDataProcessor`.

This package transforms certain FIT fields beyond the processing done by fitdecode:

- Some fields have lower- and higher-precision versions; by default, `parse()` returns only the higher-precision value, under the base field's name.
- Other fields store sub-integer precision in a separate field, which `parse()` adds into the base field.
- FIT's pedal power balance is a single bit-packed byte (a side flag plus a percentage); `parse()` decodes it into `left_balance`/`right_balance`.

Messages/fields fitdecode can't resolve against the profile (e.g. proprietary extensions) are kept as raw values under `unknown_<n>` names.

### TCX & GPX files

TCX and GPX files are parsed natively in this package.
The parser supports the following schema versions and extensions:

| Format | Schema version | Extensions |
|---|---|---|
| TCX | v2 | Garmin `ActivityExtension` v2 |
| GPX | 1.0 / 1.1 | Garmin `TrackPointExtension` v1/v2, Cluetrust `gpxdata` |

Unrecognized elements and attributes are exported as string columns named with their XML namespace in Clark notation.
