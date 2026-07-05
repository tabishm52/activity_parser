# activity-parser

[![CI](https://github.com/tabishm52/activity_parser/actions/workflows/ci.yml/badge.svg?branch=main)](https://github.com/tabishm52/activity_parser/actions/workflows/ci.yml)
[![PyPI](https://img.shields.io/pypi/v/activity-parser)](https://pypi.org/project/activity-parser/)
[![Python versions](https://img.shields.io/pypi/pyversions/activity-parser)](https://pypi.org/project/activity-parser/)
[![License](https://img.shields.io/pypi/l/activity-parser)](https://pypi.org/project/activity-parser/)

Parser for loading FIT, TCX and GPX activity files into Pandas DataFrames.

Provides a parser object for reading (optionally gzipped) FIT, TCX, and GPX activity files and converting them into Pandas DataFrames.
During import, column names extracted from activity files are normalized into a canonical set of output column names.
See [FIT files](#fit-files) and [TCX & GPX files](#tcx--gpx-files) below for format-specific details.

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

Each file is assumed to contain a single activity: multiple activities/tracks (chained FIT files, multi-activity TCX, multi-track GPX) are merged into one set of results, possibly over-writing some fields.

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
TCX has no temperature field in any known schema, so it never appears from TCX.
GPX files also have no lap data, so `laps` will always be an empty DataFrame.
Fields marked with (\*) are exporter-dependent.

`laps` follows the same convention for shared metrics (`total_distance`, `avg_speed`, `max_speed`, `avg_heart_rate`, `avg_power`, `total_calories`, etc.).
FIT also exposes FIT-specific fields not available from TCX/GPX (e.g. `fractional_cadence`, `left_right_balance`, `accumulated_power`) under their native FIT names.

## FIT files

FIT parsing wraps [`fitdecode`](https://github.com/polyvertex/fitdecode), which decodes against Garmin's public FIT SDK profile — field names, types, and units come from that profile, not this package.

- Newer devices sometimes write only `enhanced_altitude`/`enhanced_speed` (and lap `enhanced_avg_speed`/`enhanced_max_speed`); `parse()` coalesces these into `altitude`/`speed` transparently.
- Messages/fields fitdecode can't resolve against the profile (e.g. proprietary extensions) are kept as raw values under `unknown_<n>` names; `parse()`'s canonical columns still exclude them.

## TCX & GPX files

The parser supports the following schema versions and extensions:

| Format | Schema version | Extensions |
|---|---|---|
| TCX | v2 | Garmin `ActivityExtension` v2 |
| GPX | 1.0 / 1.1 | Garmin `TrackPointExtension` v1/v2, Cluetrust `gpxdata` |

Unrecognized elements and attributes are exported as string columns named with their XML namespace in Clark notation.
