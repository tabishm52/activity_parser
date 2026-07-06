"""Functions for parsing TCX and GPX files into Pandas DataFrames.

Records and laps are extracted using the schema-derived tables in ``xml_fields``. Known
elements/attributes are converted to typed, canonically-named columns. Anything else is
still collected, namespace-qualified, as an uncoerced string column so unrecognized
extensions aren't silently dropped.
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
    XSI_NS,
    Converter,
    FieldPath,
    FieldPathStep,
    XmlField,
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

    Used only for the ``extra`` metadata dict, which pulls whatever data remains once
    records/laps are removed.
    """
    # Iterating with "*" matches only true elements and drops e.g. comments
    for el in element.iter("*"):
        # Some (name, value) pairs are stored as XML attributes
        for key, value in el.attrib.items():
            qname = etree.QName(key)
            if qname.namespace == XSI_NS and qname.localname == "type":
                continue
            yield qname.localname, cast(str, value)

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
    """Yields (path, value) for every attribute and leaf element under ``element``.

    ``path`` matches the keys of the field tables in ``xml_fields``. XML comments are
    skipped.
    """
    yield from _walk(element, ())


def _walk(element: etree._Element, path: FieldPath) -> Iterator[tuple[FieldPath, str]]:
    """Recursive implementation of ``walk_fields``; ``path`` is the walk so far."""
    for key, value in element.attrib.items():
        qname = etree.QName(key)
        if qname.namespace == XSI_NS and qname.localname == "type":
            # xsi:type is schema-validation metadata, not activity data.
            continue
        yield path + ((qname.namespace, "@" + qname.localname),), cast(str, value)

    # "*" matches only true elements, so comments are skipped without special-casing.
    children = list(element.iterchildren("*"))
    if element.text is not None and not element.text.isspace():
        yield path, element.text
    for child in children:
        child_qname = etree.QName(child)
        yield from _walk(child, path + ((child_qname.namespace, child_qname.localname),))


def unknown_column_name(step: FieldPathStep) -> str:
    """Column name for a leaf not found in the field table: namespace-qualified."""
    namespace, name = step
    name = name.removeprefix("@")
    return f"{{{namespace}}}{name}" if namespace else name


def _full_path_column_name(path: FieldPath) -> str:
    """Column name for a field whose usual name collides with an earlier one in the row."""
    return "/".join(unknown_column_name(step) for step in path)


def _field_with_parent_namespace(
    path: FieldPath, fields: Mapping[FieldPath, XmlField]
) -> XmlField | None:
    """Retries a leaf with no namespace under its parent's namespace instead."""
    parent = path[:-1]
    if not parent or path[-1][0] is not None:
        return None
    parent_namespace = parent[-1][0]
    return fields.get(parent + ((parent_namespace, path[-1][1]),))


def _row_from_fields(
    element: etree._Element, fields: Mapping[FieldPath, XmlField]
) -> dict[str, str]:
    """Maps ``element``'s fields to a row dict, keyed by canonical or unknown column.

    The first path to reach a given column claims its usual name; a later, different
    path that collides with it is kept too, under its full path, rather than dropped.
    """
    row: dict[str, str] = {}
    for path, value in _walk(element, ()):
        field = fields.get(path) or _field_with_parent_namespace(path, fields)
        column = field.column if field is not None else unknown_column_name(path[-1])
        if column in row:
            column = _full_path_column_name(path)
        row[column] = value
    return row


def build_dataframe(
    elements: Iterable[etree._Element], fields: Mapping[FieldPath, XmlField]
) -> pd.DataFrame:
    """Builds a DataFrame from ``elements`` using ``fields`` for typing/renaming."""
    df = pd.DataFrame(_row_from_fields(element, fields) for element in elements)

    converts: dict[str, Converter | None] = {}
    for field in fields.values():
        converts.setdefault(field.column, field.convert)

    for col in df.columns:
        convert = converts.get(col)
        if convert is not None:
            df[col] = convert(df[col])

    return df


def _index_by_time(records: pd.DataFrame) -> pd.DataFrame:
    """Sets ``time`` as the index, dropping rows with no timestamp or a duplicate one."""
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

    Known elements/attributes are converted to typed, canonically-named columns.
    Unknown elements/attributes are returned under a namespace-qualified name, e.g.
    ``{namespace}localname``.

    Assumes that the TCX file is all one activity. Files with multiple activities will
    be merged into one set of return values, possibly over-writing some fields.

    Args:
        file: File-like or path-like object. A path-like argument ending in ``.gz`` will
            be transparently unzipped before processing.
        strict_xml: If True, raises ``lxml.etree.XMLSyntaxError`` on malformed XML. If
            False, parser recovery is enabled.

    Returns:
        Tuple containing records, laps, and additional metadata.
    """
    parser = etree.XMLParser(recover=not strict_xml)
    root = etree.parse(file, parser).getroot()

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

    Known elements/attributes are converted to typed, canonically-named columns.
    Unknown elements/attributes are returned under a namespace-qualified name, e.g.
    ``{namespace}localname``.

    Assumes that the GPX file is all one activity. Files with multiple tracks will be
    merged into one set of return values, possibly over-writing some fields. Waypoints
    and routes in the GPX file are ignored.

    Args:
        file: File-like or path-like object. A path-like argument ending in ``.gz`` will
            be transparently unzipped before processing.
        strict_xml: If True, raises ``lxml.etree.XMLSyntaxError`` on malformed XML. If
            False, parser recovery is enabled.

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
