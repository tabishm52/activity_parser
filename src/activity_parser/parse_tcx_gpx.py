"""Functions for parsing TCX and GPX files into Pandas DataFrames.

Records and laps are extracted using the schema-derived field tables in
``xml_fields``: known elements/attributes are converted to typed, canonically-named
columns; anything else is still collected, namespace-qualified, as an uncoerced string
column (see ``unknown_column_name``) so unrecognized extensions aren't silently
dropped.
"""

from collections.abc import Iterable, Iterator, Mapping
from os import PathLike
from typing import IO, cast

import pandas as pd
from lxml import etree

from .xml_fields import (
    GPX_TRACKPOINT_FIELDS,
    TCX_LAP_FIELDS,
    TCX_TRACKPOINT_FIELDS,
    Convert,
    FieldPath,
    FieldPathStep,
    XmlField,
    column_converts,
)


def remove_elements(root: etree._Element, *tags: str) -> None:
    """Remove all elements matching ``tags`` from the tree."""
    for element in root.iter(*tags):
        parent = element.getparent()
        if parent is not None:
            parent.remove(element)


def extract_xml_fields(
    element: etree._Element,
) -> Iterator[tuple[str, str | None]]:
    """Yields (name, value) pairs recursively through an XML element.

    Used for the ``extra`` metadata dict, which is intentionally left as a raw,
    non-canonical slurp of whatever remains once records/laps are removed.
    """
    # Iterating with "*" matches only true elements and drops e.g. comments
    for el in element.iter("*"):
        # Some (name, value) pairs are stored as XML attributes
        for key, value in el.attrib.items():
            localname = etree.QName(key).localname
            if localname != "type":
                yield localname, cast(str, value)

        # In a TCX file, some values are buried in a 'Value' element
        if el.text is None or el.text.isspace():
            try:
                child = next(el.iterchildren("*"))
                parent_localname = etree.QName(el).localname
                child_localname = etree.QName(child).localname
                if child_localname == "Value":
                    yield parent_localname, child.text
            except StopIteration:
                pass

        # But most values are recorded as leaf element text
        else:
            localname = etree.QName(el).localname
            if localname != "Value":
                yield localname, el.text


def walk_fields(element: etree._Element) -> Iterator[tuple[FieldPath, str]]:
    """Yields (path, value) pairs for every attribute and leaf element under ``element``.

    ``path`` is the sequence of ``(namespace, localname)`` steps from ``element`` down
    to the attribute or leaf, matching the keys of the tables in ``xml_fields``.
    Attribute steps are marked with a "@" localname prefix. Comments are skipped
    automatically by iterating children with ``"*"``.
    """
    yield from _walk(element, ())


def _walk(element: etree._Element, path: FieldPath) -> Iterator[tuple[FieldPath, str]]:
    for key, value in element.attrib.items():
        qname = etree.QName(key)
        if qname.localname == "type":
            continue
        yield path + ((qname.namespace, "@" + qname.localname),), cast(str, value)

    children = list(element.iterchildren("*"))
    if element.text is not None and not element.text.isspace():
        yield path, element.text
    elif children:
        for child in children:
            child_qname = etree.QName(child)
            yield from _walk(child, path + ((child_qname.namespace, child_qname.localname),))


def unknown_column_name(step: FieldPathStep) -> str:
    """Column name for a leaf not found in the field table: namespace-qualified."""
    namespace, name = step
    name = name.removeprefix("@")
    return f"{{{namespace}}}{name}" if namespace else name


def _row_from_fields(
    element: etree._Element, fields: Mapping[FieldPath, XmlField]
) -> dict[str, str]:
    row: dict[str, str] = {}
    for path, value in _walk(element, ()):
        field = fields.get(path)
        column = field.column if field is not None else unknown_column_name(path[-1])
        row.setdefault(column, value)
    return row


def build_dataframe(
    elements: Iterable[etree._Element], fields: Mapping[FieldPath, XmlField]
) -> pd.DataFrame:
    """Builds a DataFrame from ``elements`` using ``fields`` for typing/renaming."""
    df = pd.DataFrame(_row_from_fields(element, fields) for element in elements)
    converts = column_converts(fields)

    for col in df.columns:
        convert = converts.get(col)
        if convert is None or convert is Convert.STRING:
            continue

        if convert is Convert.DATETIME:
            # Without format="ISO8601", timestamps mixing naive and UTC-offset values in
            # the same column silently become NaT instead of parsing.
            df[col] = pd.to_datetime(df[col], errors="coerce", utc=True, format="ISO8601")
            continue

        values = df[col]
        non_null = values.notna().sum()
        if non_null == 0:
            continue

        numeric_values = pd.to_numeric(values, errors="coerce")
        if numeric_values.notna().sum() != non_null:
            # Some values genuinely aren't numeric; leave the column as raw strings
            # rather than partially coercing it.
            continue

        # Conversion from meters and m/s to km and kph is done to align with processing
        # done by fitdecode.StandardUnitsDataProcessor
        if convert is Convert.NUMERIC_M_TO_KM:
            df[col] = numeric_values / 1000.0
        elif convert is Convert.NUMERIC_MS_TO_KMH:
            df[col] = numeric_values * 3.6
        else:
            df[col] = numeric_values

    return df


def _index_by_time(records: pd.DataFrame) -> pd.DataFrame:
    if "time" not in records.columns:
        records["time"] = pd.NaT
    records = records.set_index("time")
    records = records[records.index.notna()]
    return records[~records.index.duplicated()]


def parse_tcx(
    file: str | PathLike[str] | IO[str] | IO[bytes],
    strict_xml: bool = False,
) -> tuple[pd.DataFrame, pd.DataFrame, dict[str, str | None]]:
    """Loads a TCX activity into Pandas DataFrames.

    Assumes that the TCX file is all one activity. Files with multiple activities will
    be merged into one set of return values, possibly over-writing some fields.

    Args:
        file: File-like or path-like object. A path-like argument ending in ``.gz`` will
            be transparently unzipped before processing.
        strict_xml: If True, fail on XML parsing errors instead of recovering.

    Returns:
        Tuple containing records, laps, and additional metadata.
    """
    # lxml takes care of identifying and handling a gzipped file
    parser = etree.XMLParser(recover=not strict_xml)
    root = etree.parse(file, parser).getroot()

    # TCX files occasionally have duplicate timestamps, just drop those
    records = build_dataframe(root.iter("{*}Trackpoint"), TCX_TRACKPOINT_FIELDS)
    records = _index_by_time(records)

    remove_elements(root, "{*}Track")

    laps = build_dataframe(root.iter("{*}Lap"), TCX_LAP_FIELDS)

    remove_elements(root, "{*}Lap")

    extra = dict(extract_xml_fields(root))
    extra.pop("schemaLocation", None)

    return records, laps, extra


def parse_gpx(
    file: str | PathLike[str] | IO[str] | IO[bytes],
    strict_xml: bool = False,
) -> tuple[pd.DataFrame, pd.DataFrame, dict[str, str | None]]:
    """Loads a GPX activity into a Pandas DataFrame.

    Assumes that the GPX file is all one activity. Files with multiple tracks will be
    merged into one set of return values, possibly over-writing some fields. Waypoints
    and routes in the GPX file are ignored.

    Args:
        file: File-like or path-like object. A path-like argument ending in ``.gz`` will
            be transparently unzipped before processing.
        strict_xml: If True, fail on XML parsing errors instead of recovering.

    Returns:
        Tuple containing records, laps, and additional metadata. Note GPX files don't
        have lap information, so the laps DataFrame will be empty.
    """
    parser = etree.XMLParser(recover=not strict_xml)
    root = etree.parse(file, parser).getroot()

    records = build_dataframe(root.iter("{*}trkpt"), GPX_TRACKPOINT_FIELDS)
    records = _index_by_time(records)

    remove_elements(root, "{*}trkseg", "{*}rte", "{*}wpt")

    extra = dict(extract_xml_fields(root))
    extra.pop("schemaLocation", None)

    return records, pd.DataFrame(), extra
