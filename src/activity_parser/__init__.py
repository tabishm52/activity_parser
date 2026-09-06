"""Parser for loading FIT, TCX and GPX files into Pandas DataFrames."""

from .activity import Activity
from .exceptions import FitError, ParseError, XmlError
from .parse_fit import parse_fit, parse_fit_raw
from .parse_tcx_gpx import parse_gpx, parse_tcx
from .parser import ActivityParser

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
