# activity-parser

[![CI](https://github.com/tabishm52/activity_parser/actions/workflows/ci.yml/badge.svg?branch=main)](https://github.com/tabishm52/activity_parser/actions/workflows/ci.yml)

Parser for loading FIT, TCX and GPX activity files into Pandas DataFrames.

Provides a parser object for reading (optionally gzipped) FIT, TCX, and GPX activity files and converting them into Pandas DataFrames.
During import, column names extracted from activity files are normalized into a canonical set of output column names.

## Installation

```bash
pip install git+https://github.com/tabishm52/activity_parser.git
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

Regardless of source format, `records` and `laps` use a canonical set of column names, e.g.:

```
                           distance  speed  cadence  heart_rate
time
2026-01-05 08:00:00+00:00      0.00   36.0       80         100
2026-01-05 08:00:01+00:00      0.01   36.0       81         101
```

## Output columns

Units are aligned to FIT's standard units (via `fitdecode.StandardUnitsDataProcessor`), and columns are renamed/converted where needed so the same name means the same unit regardless of source format:

| Column | Unit | FIT | TCX | GPX |
|---|---|:-:|:-:|:-:|
| `latitude`, `longitude` | degrees | Yes | Yes | Yes |
| `altitude` | meters | Yes | Yes | Yes |
| `distance` | km | Yes | Yes | — |
| `speed` | km/h | Yes | Yes | (\*) |
| `cadence` | rpm | Yes | Yes | Yes |
| `heart_rate` | bpm | Yes | Yes | Yes |
| `power` | watts | Yes | Yes | Yes |
| `temperature` | °C | Yes | — | Yes |

Not every column appears in every file: `parse()` only includes columns actually present in the source. Two of these gaps are structural — GPX has no field for cumulative distance (in the base spec or in Garmin's `TrackPointExtension`), and TCX has no field for temperature (in the base spec or in Garmin's `ActivityExtension`) — so those will never appear regardless of exporter. GPX files also have no lap data, so `laps` will always be an empty DataFrame.

(\*) `speed` for GPX is exporter-dependent, not a format limitation: it's defined in Garmin's `TrackPointExtension/v2` schema, but Garmin Connect's GPX exports currently use `v1`, which predates that field. Files from tools/devices that do emit `v2` (or any other extension exposing a `speed`-named field) will have it picked up and converted from m/s to km/h like the other formats.

`laps` follows the same convention for shared metrics (`total_distance`, `avg_speed`, `max_speed`, `avg_heart_rate`, `avg_power`, `total_calories`, etc.). FIT also exposes FIT-specific fields not available from TCX/GPX — e.g. `fractional_cadence`, `left_right_balance`, `accumulated_power` — under their native FIT names.

## License

MIT
