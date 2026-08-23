"""Functions for parsing TCX and GPX files into Pandas DataFrames.

Records and laps are extracted using the schema-derived tables in ``xml_fields``. Known
elements/attributes are converted to typed, canonically-named columns. Anything else is
still collected, namespace-qualified, as an uncoerced string column so unrecognized
extensions aren't silently dropped.
"""

from collections.abc import Iterable, Iterator, Mapping
from functools import cache
from os import PathLike
from typing import IO, cast

import pandas as pd
from lxml import etree

from .exceptions import XmlError
from .output import Activity
from .postprocess import index_by_time
from .xml_fields import (
    GPX_TRACKPOINT_FIELDS,
    TCX_LAP_FIELDS,
    TCX_TRACKPOINT_FIELDS,
    XSI_NS,
    Converter,
    FieldPath,
    FieldPathStep,
    XmlField,
    to_datetime,
)


def parse_xml_root(
    file: str | PathLike[str] | IO[str] | IO[bytes], strict_xml: bool
) -> etree._Element:
    """Parses ``file`` into an XML root element, raising ``XmlError`` on malformed XML."""
    parser = etree.XMLParser(recover=not strict_xml)
    try:
        root = etree.parse(file, parser).getroot()
    except etree.XMLSyntaxError as e:
        raise XmlError(str(e)) from e
    if root is None:
        raise XmlError("No parseable XML content found.")
    return root


def remove_elements(root: etree._Element, *tags: str) -> None:
    """Removes all elements matching ``tags`` from the tree."""
    for element in root.iter(*tags):
        parent = element.getparent()
        if parent is not None:
            parent.remove(element)


def _parse_timestamp(text: str | None) -> pd.Timestamp | None:
    """Parses a single ISO8601 timestamp, or ``None`` if absent/unparseable."""
    if text is None:
        return None
    parsed = to_datetime(pd.Series([text])).iloc[0]
    return None if pd.isna(parsed) else parsed


def _find_text(element: etree._Element | None, tag: str) -> str | None:
    """``element.find(tag).text``, tolerating a missing ``element`` or child."""
    if element is None:
        return None
    child = element.find(tag)
    return child.text if child is not None else None


def tcx_activity(root: etree._Element) -> Activity:
    """Builds an ``Activity`` summary from a TCX file's (first) ``Activity`` element."""
    activity_el = root.find(".//{*}Activity")
    if activity_el is None:
        return Activity()

    creator_el = activity_el.find("{*}Creator")
    return Activity(
        sport=activity_el.get("Sport"),
        start_time=_parse_timestamp(_find_text(activity_el, "{*}Id")),
        creator=_find_text(creator_el, "{*}Name"),
        notes=_find_text(activity_el, "{*}Notes"),
    )


def gpx_activity(root: etree._Element) -> Activity:
    """Builds an ``Activity`` summary from a GPX file's root/``metadata`` elements."""
    metadata_el = root.find("{*}metadata")
    return Activity(
        start_time=_parse_timestamp(_find_text(metadata_el, "{*}time")),
        creator=root.get("creator"),
        notes=_find_text(metadata_el, "{*}desc"),
    )


def walk_fields(element: etree._Element) -> Iterator[tuple[FieldPath, str]]:
    """Yields (path, value) for every attribute and leaf element under ``element``.

    ``path`` matches the keys of the field tables in ``xml_fields``. XML comments are
    skipped.
    """
    yield from _walk(element, ())


@cache
def _split_tag(tag: str) -> FieldPathStep:
    """Splits an lxml ``{namespace}localname`` tag into a ``FieldPath`` step."""
    if tag.startswith("{"):
        namespace, _, localname = tag[1:].partition("}")
        return namespace, localname
    return None, tag


def _walk(element: etree._Element, path: FieldPath) -> Iterator[tuple[FieldPath, str]]:
    """Recursive implementation of ``walk_fields``; ``path`` is the walk so far."""
    for key, value in element.attrib.items():
        namespace, localname = _split_tag(key)
        if namespace == XSI_NS and localname == "type":
            # xsi:type is schema-validation metadata, not activity data.
            continue
        yield path + ((namespace, "@" + localname),), cast(str, value)

    text = element.text
    if text is not None and not text.isspace():
        yield path, text
    # "*" matches only true elements, so comments are skipped without special-casing.
    for child in element.iterchildren("*"):
        yield from _walk(child, path + (_split_tag(child.tag),))


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
    for path, value in walk_fields(element):
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


def parse_tcx(
    file: str | PathLike[str] | IO[str] | IO[bytes],
    strict_xml: bool = False,
) -> tuple[pd.DataFrame, pd.DataFrame, Activity]:
    """Loads a TCX activity into Pandas DataFrames.

    Known elements/attributes are converted to typed, canonically-named columns.
    Unknown elements/attributes are returned under a namespace-qualified name, e.g.
    ``{namespace}localname``.

    Assumes that the TCX file is all one activity. If a file has multiple ``Activity``
    elements, only the first is used to build the returned ``Activity`` summary; records
    and laps from all of them are still merged together.

    Args:
        file: File-like or path-like object. A path-like argument ending in ``.gz`` will
            be transparently unzipped before processing.
        strict_xml: If True, requires well-formed XML. If False, parser recovery is
            enabled.

    Returns:
        Tuple containing records, laps, and an ``Activity`` summary.

    Raises:
        XmlError: The file's XML fails to parse (e.g. no XML content at all, or, when
            ``strict_xml`` is True, malformed XML).
    """
    root = parse_xml_root(file, strict_xml)

    records = build_dataframe(root.iter("{*}Trackpoint"), TCX_TRACKPOINT_FIELDS)
    records = index_by_time(records, "time")

    # Strip Track/Trackpoint first: each Lap's walk is recursive, so without this its
    # nested Trackpoint fields would be misattributed as unrecognized Lap-level columns.
    remove_elements(root, "{*}Track")
    laps = build_dataframe(root.iter("{*}Lap"), TCX_LAP_FIELDS)

    activity = tcx_activity(root)

    return records, laps, activity


def parse_gpx(
    file: str | PathLike[str] | IO[str] | IO[bytes],
    strict_xml: bool = False,
) -> tuple[pd.DataFrame, pd.DataFrame, Activity]:
    """Loads a GPX activity into Pandas DataFrames.

    Known elements/attributes are converted to typed, canonically-named columns.
    Unknown elements/attributes are returned under a namespace-qualified name, e.g.
    ``{namespace}localname``.

    Assumes that the GPX file is all one activity. Files with multiple tracks will have
    their points merged into one set of records. Waypoints and routes in the GPX file
    are ignored.

    Args:
        file: File-like or path-like object. A path-like argument ending in ``.gz`` will
            be transparently unzipped before processing.
        strict_xml: If True, requires well-formed XML. If False, parser recovery is
            enabled.

    Returns:
        Tuple containing records, laps, and an ``Activity`` summary. Note GPX files
        don't have lap information, so the laps DataFrame will be empty.

    Raises:
        XmlError: The file's XML fails to parse (e.g. no XML content at all, or, when
            ``strict_xml`` is True, malformed XML).
    """
    root = parse_xml_root(file, strict_xml)

    records = build_dataframe(root.iter("{*}trkpt"), GPX_TRACKPOINT_FIELDS)
    records = index_by_time(records, "time")

    activity = gpx_activity(root)

    return records, pd.DataFrame(), activity
