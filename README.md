# activity-parser

[![CI](https://github.com/tabishm52/activity_parser/actions/workflows/ci.yml/badge.svg?branch=main)](https://github.com/tabishm52/activity_parser/actions/workflows/ci.yml)
[![PyPI](https://img.shields.io/pypi/v/activity-parser)](https://pypi.org/project/activity-parser/)
[![Python versions](https://img.shields.io/pypi/pyversions/activity-parser)](https://pypi.org/project/activity-parser/)
[![License](https://img.shields.io/pypi/l/activity-parser)](https://pypi.org/project/activity-parser/)

Parser for loading FIT, TCX and GPX activity files into Pandas DataFrames.

Provides a parser object for reading (optionally gzipped) FIT, TCX, and GPX activity files and converting them into Pandas DataFrames.
During import, column names extracted from activity files are normalized into a canonical set of output column names.

TCX and GPX parsing is schema-derived: elements and attributes are matched against declarative field tables transcribed from the TCX v2, GPX 1.0/1.1, and known extension (Garmin `ActivityExtension`/`TrackPointExtension` v1/v2, Cluetrust `gpxdata`) XSDs, rather than slurped indiscriminately by name.
Anything not in those tables is still collected rather than dropped — see [Unrecognized elements](#unrecognized-elements) below.

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
records, laps, extra = parser.parse('path/to/fit_file.fit')
records, laps, extra = parser.parse('path/to/gpx_file.gpx')
records, laps, extra = parser.parse('path/to/tcx_file.tcx')
```

Regardless of source format, `records` and `laps` use a canonical set of column names (see [Output columns](#output-columns) below), e.g.:

```
                           distance  speed  cadence  heart_rate
time
2026-01-05 08:00:00+00:00      0.00   36.0       80         100
2026-01-05 08:00:01+00:00      0.01   36.0       81         101
```

`extra` is not canonicalized like `records` and `laps`: it's a dict of leftover, format-specific metadata passed through with its native field names, and its shape differs by format.
For FIT, it's keyed by FIT message name (e.g. `session`, `device_info`).
For TCX/GPX, it's a single dict of the root element's attributes/fields (e.g. `Creator`, `Id`).
Treat it as raw metadata to inspect per-format rather than something to consume generically.

## Output columns

Units are aligned to FIT's standard units (via `fitdecode.StandardUnitsDataProcessor`), and columns are renamed/converted where needed so the same name means the same unit regardless of source format:

| Column | Unit | FIT | TCX | GPX |
|---|---|:-:|:-:|:-:|
| `latitude`, `longitude` | degrees | Yes | Yes | Yes |
| `altitude` | meters | Yes | Yes | Yes |
| `distance` | km | Yes | Yes | (\*) |
| `speed` | km/h | Yes | Yes | (\*) |
| `cadence` | rpm | Yes | Yes | Yes |
| `heart_rate` | bpm | Yes | Yes | Yes |
| `power` | watts | Yes | Yes | Yes |
| `temperature` | °C | Yes | — | Yes |

Not every column appears in every file: `parse()` only includes columns actually present in the source.
TCX has no field for temperature, in the base spec or in Garmin's `ActivityExtension`, so that column will never appear from a TCX file regardless of exporter.
GPX files also have no lap data, so `laps` will always be an empty DataFrame.

(\*) `speed` and GPX `distance` are exporter-dependent, not a format limitation: `speed` comes from Garmin's `TrackPointExtension` (v1 or v2), and per-point `distance` from Cluetrust's `gpxdata` extension.
Any exporter emitting one of the recognized extension schemas (see `activity_parser.xml_fields`) will have it picked up and normalized.

`laps` follows the same convention for shared metrics (`total_distance`, `avg_speed`, `max_speed`, `avg_heart_rate`, `avg_power`, `total_calories`, etc.).
FIT also exposes FIT-specific fields not available from TCX/GPX (e.g. `fractional_cadence`, `left_right_balance`, `accumulated_power`) under their native FIT names.

TCX/GPX records and laps also expose other fields beyond this core set — e.g. `course`/`bearing`, `water_temperature`, `depth`, `sensor_state`, and lap fields like `intensity`, `notes`, `total_strides`.
GPS-fix-quality diagnostics (`hdop`, `vdop`, `pdop`, `satellites`, `fix_type`, ...) and static descriptive labels (`name`, `cmt`, `desc`, ...) are schema-known but aren't fitness data, so they're left out of the canonical selector; use the lower-level `parse_tcx`/`parse_gpx` if you need them.
See `activity_parser.xml_fields` for the full field tables, or `parser.tcx_records_selector` / `parser.gpx_records_selector` / `parser.tcx_laps_selector` for the exact canonical column set and order each format can produce.

## Unrecognized elements

TCX/GPX elements and attributes that aren't in the known schema tables aren't dropped: `parse_tcx`/`parse_gpx` still collect them as string columns, named with their XML namespace in Clark notation (e.g. `{http://example.com/some-vendor-extension}stress`), with no numeric coercion applied.
This means a device or app using an extension schema this library doesn't know about won't silently lose data — inspect the column names to see what showed up.
If two different fields would otherwise produce the same column name (e.g. two unrelated extensions both using a leaf named `value`), the first keeps that name and later ones fall back to a column named after their full path instead of being dropped.

`ActivityParser.parse()` (the high-level entry point) filters these out, returning only the canonical columns listed above.
Use the lower-level `parse_tcx`/`parse_gpx` functions directly if you need access to unrecognized columns.
