"""Parsing exceptions, decoupled from the decoding backend."""


class ParseError(Exception):
    """Base for parsing failures across FIT, TCX, and GPX activity files."""


class FitError(ParseError):
    """Raised when a FIT file fails to parse (e.g. invalid header, CRC mismatch)."""


class XmlError(ParseError):
    """Raised when a TCX or GPX file fails to parse due to malformed XML."""
