"""Tests for extension handling, column selection, and parse dispatch."""

import io
from pathlib import Path

import pandas as pd
import pytest

from activity_parser import ActivityParser
from activity_parser.parse_activity import (
    coalesce_enhanced_columns,
    infer_extension,
    normalize_extension,
    select_and_rename_cols,
)


def test_normalize_extension_case_and_dot():
    assert normalize_extension("FIT") == "fit"
    assert normalize_extension(".gpx") == "gpx"
    assert normalize_extension("Tcx") == "tcx"


def test_normalize_extension_bare_gz_rejected():
    with pytest.raises(ValueError, match="Ambiguous"):
        normalize_extension(".gz")
    with pytest.raises(ValueError, match="Ambiguous"):
        normalize_extension("gz")


def test_infer_extension():
    assert infer_extension("ride.fit") == "fit"
    assert infer_extension("ride.tcx.gz") == "tcx"
    assert infer_extension("dir/sub/ride.GPX.GZ") == "gpx"


def test_select_and_rename_cols():
    df = pd.DataFrame({"b": [1], "a": [2], "ignored": [3]})
    out = select_and_rename_cols(df, ["a", "b", "missing"], {"a": "x"})
    assert list(out.columns) == ["x", "b"]
    assert out["x"].iloc[0] == 2


def test_coalesce_enhanced_columns_prefers_enhanced_when_both_present():
    df = pd.DataFrame({"altitude": [100.0, 200.0], "enhanced_altitude": [105.0, 210.0]})
    out = coalesce_enhanced_columns(df, {"altitude": "enhanced_altitude"})
    assert list(out["altitude"]) == [105.0, 210.0]


def test_coalesce_enhanced_columns_falls_back_to_base_where_enhanced_is_null():
    df = pd.DataFrame({"speed": [10.0, 20.0], "enhanced_speed": [15.0, None]})
    out = coalesce_enhanced_columns(df, {"speed": "enhanced_speed"})
    assert list(out["speed"]) == [15.0, 20.0]


def test_coalesce_enhanced_columns_fills_missing_base_column():
    df = pd.DataFrame({"enhanced_speed": [10.0, 20.0]})
    out = coalesce_enhanced_columns(df, {"speed": "enhanced_speed"})
    assert list(out["speed"]) == [10.0, 20.0]


def test_coalesce_enhanced_columns_noop_without_enhanced_column():
    df = pd.DataFrame({"altitude": [100.0, 200.0]})
    out = coalesce_enhanced_columns(df, {"altitude": "enhanced_altitude"})
    assert list(out["altitude"]) == [100.0, 200.0]
    assert "enhanced_altitude" not in out.columns


def test_parse_file_like_requires_ext():
    with pytest.raises(ValueError, match="ext must be provided"):
        ActivityParser().parse(io.BytesIO(b""))


def test_parse_unsupported_extension():
    with pytest.raises(ValueError, match="not supported"):
        ActivityParser().parse("ride.kml")


def test_parse_explicit_ext_overrides_path(tmp_path):
    # ext takes precedence over the path suffix
    src = Path(__file__).parent / "files" / "gpx" / "sample.gpx"
    odd_name = tmp_path / "export.dat"
    odd_name.write_bytes(src.read_bytes())

    records, _, _ = ActivityParser().parse(odd_name, ext="gpx")
    assert len(records) == 3


def test_tcx_columns_match_selector_order():
    # parse_tcx already emits canonical names; ActivityParser only selects/orders them,
    # dropping any namespace-qualified columns for unrecognized elements.
    parser = ActivityParser()
    records, laps, _ = parser.parse(Path(__file__).parent / "files" / "tcx" / "sample.tcx")
    assert list(records.columns) == [c for c in parser.tcx_records_selector if c in records.columns]
    assert list(laps.columns) == [c for c in parser.tcx_laps_selector if c in laps.columns]


def test_gpx_columns_match_selector_order():
    parser = ActivityParser()
    records, _, _ = parser.parse(Path(__file__).parent / "files" / "gpx" / "sample.gpx")
    assert list(records.columns) == [c for c in parser.gpx_records_selector if c in records.columns]
