"""Parser for loading FIT, TCX and GPX files into Pandas DataFrames."""

from .exceptions import FitError, ParseError, XmlError
from .output import Activity
from .parse_activity import ActivityParser
from .parse_fit_file import parse_fit, parse_fit_raw
from .parse_tcx_gpx import parse_gpx, parse_tcx

__all__ = [
    "Activity",
    "ActivityParser",
    "FitError",
    "ParseError",
    "XmlError",
    "parse_fit",
    "parse_fit_raw",
    "parse_gpx",
    "parse_tcx",
]
