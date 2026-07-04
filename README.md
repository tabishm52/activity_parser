# activity-parser

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

## License

MIT
