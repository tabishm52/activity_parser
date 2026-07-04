"""Functions for parsing TCX and GPX files into Pandas DataFrames."""

from collections.abc import Iterator
from os import PathLike
from typing import IO, cast

import pandas as pd
from lxml import etree

NUMERIC_EXACT_COLUMNS = {
    "lat",
    "lon",
    "ele",
    "hr",
    "cad",
    "power",
    "atemp",
    "speed",
    "Watts",
    "DistanceMeters",
    "AltitudeMeters",
    "HeartRateBpm",
    "Cadence",
    "LatitudeDegrees",
    "LongitudeDegrees",
}

NUMERIC_SUBSTRINGS = (
    "Distance",
    "Speed",
    "Altitude",
    "Cadence",
    "HeartRate",
    "Watts",
    "Power",
    "Calories",
)


def should_coerce_numeric(column_name: str) -> bool:
    """Return True when an XML-derived column should be numeric."""
    if column_name in NUMERIC_EXACT_COLUMNS:
        return True
    return any(token in column_name for token in NUMERIC_SUBSTRINGS)


def remove_elements(root: etree._Element, *tags: str) -> None:
    """Remove all elements matching ``tags`` from the tree."""
    for element in root.iter(*tags):
        parent = element.getparent()
        if parent is not None:
            parent.remove(element)


def extract_xml_fields(
    element: etree._Element,
) -> Iterator[tuple[str, str | None]]:
    """Yields (name, value) pairs recursively through an XML element."""
    for el in element.iter():
        # Some (name, value) pairs are stored as XML attributes
        for key, value in el.attrib.items():
            localname = etree.QName(key).localname
            if localname != "type":
                yield localname, cast(str, value)

        # In a TCX file, some values are buried in a 'Value' element
        if el.text is None or el.text.isspace():
            try:
                child = next(el.iterchildren())
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


def cleanup_xml_dataframe(df: pd.DataFrame, time_col: str) -> pd.DataFrame:
    """Common post-processing for DataFrames extracted from XML elements."""
    for col in df.columns:
        if col == time_col or not should_coerce_numeric(str(col)):
            continue

        values = df[col]
        non_null = values.notna().sum()
        if non_null == 0:
            continue

        numeric_values = pd.to_numeric(values, errors="coerce")
        if numeric_values.notna().sum() == non_null:
            df[col] = numeric_values

    if time_col in df.columns:
        df[time_col] = pd.to_datetime(df[time_col], errors="coerce")
    else:
        df[time_col] = pd.NaT

    # Conversion from meters and m/s to km and kph is done to align with
    # processing done by fitdecode.StandardUnitsDataProcessor
    for col in df.columns:
        if "distance" in col.lower():
            df[col] = df[col] / 1000.0
            df = df.rename(columns={col: col.replace("Meters", "Km")})
        if "speed" in col.lower():
            df[col] = df[col] * 60.0 * 60.0 / 1000.0

    return df


def parse_tcx(
    file: str | PathLike[str] | IO[str] | IO[bytes],
    strict_xml: bool = False,
) -> tuple[pd.DataFrame, pd.DataFrame, dict[str, str | None]]:
    """Loads a TCX activity into Pandas DataFrames.

    Assumes that the TCX file is all one activity. Files with multiple
    activities will be merged into one set of return values, possibly
    over-writing some fields.

    Args:
        file: File-like or path-like object. A path-like argument ending in
            '.gz' will be transparently unzipped before processing.
        strict_xml: If True, fail on XML parsing errors instead of recovering.

    Returns:
        Tuple containing records, laps, and additional metadata.
    """
    # lxml takes care of identifying and handling a gzipped file
    parser = etree.XMLParser(recover=not strict_xml)
    root = etree.parse(file, parser).getroot()

    # TCX files occasionally have duplicate timestamps, just drop those
    records = pd.DataFrame(
        dict(extract_xml_fields(element))
        for element in root.iter("{*}Trackpoint")
    )
    records = cleanup_xml_dataframe(records, "Time").set_index("Time")
    records = records[records.index.notna()]
    records = records[~records.index.duplicated()]

    remove_elements(root, "{*}Track")

    laps = pd.DataFrame(
        dict(extract_xml_fields(element)) for element in root.iter("{*}Lap")
    )
    laps = cleanup_xml_dataframe(laps, "StartTime")

    remove_elements(root, "{*}Lap")

    extra = dict(extract_xml_fields(root))
    extra.pop("schemaLocation", None)

    return records, laps, extra


def parse_gpx(
    file: str | PathLike[str] | IO[str] | IO[bytes],
    strict_xml: bool = False,
) -> tuple[pd.DataFrame, pd.DataFrame, dict[str, str | None]]:
    """Loads a GPX activity into a Pandas DataFrame.

    Assumes that the GPX file is all one activity. Files with multiple tracks
    will be merged into one set of return values, possibly over-writing some
    fields. Waypoints and routes in the GPX file are ignored.

    Args:
        file: File-like or path-like object. A path-like argument ending in
            '.gz' will be transparently unzipped before processing.
        strict_xml: If True, fail on XML parsing errors instead of recovering.

    Returns:
        Tuple containing records, laps, and additional metadata. Note GPX files
        don't have lap information, so the laps DataFrame will be empty.
    """
    # Note there is a 'gpxpy' library that provides comprehensive handling of
    # GPX files. For GPX files generated by Strava and Garmin Connect it works
    # well enough to suck the data straight out of the XML like we do above for
    # TCX files.

    parser = etree.XMLParser(recover=not strict_xml)
    root = etree.parse(file, parser).getroot()

    records = pd.DataFrame(
        dict(extract_xml_fields(element)) for element in root.iter("{*}trkpt")
    )
    records = cleanup_xml_dataframe(records, "time").set_index("time")
    records = records[records.index.notna()]
    records = records[~records.index.duplicated()]

    remove_elements(root, "{*}trkseg", "{*}rte", "{*}wpt")

    extra = dict(extract_xml_fields(root))
    extra.pop("schemaLocation", None)

    return records, pd.DataFrame(), extra
