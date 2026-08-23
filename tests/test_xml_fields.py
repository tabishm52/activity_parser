"""Tests for the declarative schema field tables themselves."""

import re

import pytest

from activity_parser.xml_fields import (
    AEXT_NS,
    GPX10_NS,
    GPX11_NS,
    GPX_TRACKPOINT_FIELDS,
    GPXDATA_NS,
    NUMERIC,
    TCX_LAP_FIELDS,
    TCX_NS,
    TCX_TRACKPOINT_FIELDS,
    TPX1_NS,
    TPX2_NS,
    XmlField,
)

ALL_TABLES = {
    "TCX_TRACKPOINT_FIELDS": TCX_TRACKPOINT_FIELDS,
    "TCX_LAP_FIELDS": TCX_LAP_FIELDS,
    "GPX_TRACKPOINT_FIELDS": GPX_TRACKPOINT_FIELDS,
}

CANONICAL_NAME = re.compile(r"^[a-z][a-z0-9_]*$")


@pytest.mark.parametrize("table_name", ALL_TABLES)
def test_canonical_names_are_snake_case(table_name):
    for field in ALL_TABLES[table_name].values():
        assert CANONICAL_NAME.match(field.column), field.column


@pytest.mark.parametrize(
    "namespace", [TCX_NS, AEXT_NS, GPX10_NS, GPX11_NS, TPX1_NS, TPX2_NS, GPXDATA_NS]
)
def test_every_namespace_is_used(namespace):
    all_paths = [path for table in ALL_TABLES.values() for path in table]
    assert any(namespace == step[0] for path in all_paths for step in path), (
        f"{namespace} unused in any field table"
    )


@pytest.mark.parametrize("table_name", ALL_TABLES)
def test_no_conflicting_converts_within_table(table_name):
    # Column collisions resolve first-wins by document order, so every entry mapping to
    # one column must agree on its conversion.
    converts = {}
    for field in ALL_TABLES[table_name].values():
        assert converts.setdefault(field.column, field.convert) == field.convert, field.column


def test_gpx10_and_gpx11_share_base_fields():
    gpx10_altitude = GPX_TRACKPOINT_FIELDS[((GPX10_NS, "ele"),)]
    gpx11_altitude = GPX_TRACKPOINT_FIELDS[((GPX11_NS, "ele"),)]
    assert gpx10_altitude == gpx11_altitude == XmlField("altitude", NUMERIC)


def test_gpx10_has_no_extensions_wrapper_fields():
    # GPX 1.0's wptType has no <extensions> element; course/speed are direct children.
    assert ((GPX10_NS, "course"),) in GPX_TRACKPOINT_FIELDS
    assert ((GPX10_NS, "extensions"), (GPX10_NS, "power")) not in GPX_TRACKPOINT_FIELDS
