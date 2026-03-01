"""Parser for loading FIT, TCX and GPX files into Pandas DataFrames.

Provides a parser object for reading (optionally gzipped) FIT, TCX, and GPX
activity files and converting them into Pandas DataFrames. During import,
column names extracted from activity files are normalized into a canonical set
of output column names.

Usage:

Create a new instance of the ActivityParser class to be reused for subsequent
parsing of activity files:

>>> import activity_parser
>>> parser = activity_parser.ActivityParser()

Parse FIT, TCX and GPX files into normalized DataFrames:

>>> records, laps, extra = parser.parse('path/to/fit_file.fit')
>>> records, laps, extra = parser.parse('path/to/gpx_file.gpx')
>>> records, laps, extra = parser.parse('path/to/tcx_file.tcx')
"""

from .parse_fit_file import parse_fit
from .parse_tcx_gpx import parse_tcx
from .parse_tcx_gpx import parse_gpx
from .parse_activity import ActivityParser
