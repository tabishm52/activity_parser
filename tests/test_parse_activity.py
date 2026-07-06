"""Tests for extension handling, column selection, and parse dispatch."""

import io
from pathlib import Path

import pandas as pd
import pytest

from activity_parser import ActivityParser
from activity_parser.parse_activity import (
    infer_extension,
    normalize_extension,
    select_and_reorder_cols,
)
from activity_parser.xml_fields import TCX_NS


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


def test_select_and_reorder_cols_selects_and_orders():
    df = pd.DataFrame({"b": [1], "a": [2], "ignored": [3]})
    out = select_and_reorder_cols(df, ["a", "b", "missing"], include_all_columns=False)
    assert list(out.columns) == ["a", "b"]
    assert out["a"].iloc[0] == 2


def test_select_and_reorder_cols_drops_extras_by_default():
    df = pd.DataFrame({"a": [1], "extra": [2]})
    out = select_and_reorder_cols(df, ["a"], include_all_columns=False)
    assert list(out.columns) == ["a"]


def test_select_and_reorder_cols_appends_extras_when_included():
    df = pd.DataFrame({"b": [1], "a": [2], "extra1": [3], "extra2": [4]})
    out = select_and_reorder_cols(df, ["a", "b"], include_all_columns=True)
    assert list(out.columns) == ["a", "b", "extra1", "extra2"]


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


def test_tcx_columns_match_canonical_order():
    # parse_tcx already emits canonical names; ActivityParser only selects/orders them,
    # dropping any namespace-qualified columns for unrecognized elements.
    parser = ActivityParser()
    records, laps, _ = parser.parse(Path(__file__).parent / "files" / "tcx" / "sample.tcx")
    assert list(records.columns) == [c for c in parser.record_columns if c in records.columns]
    assert list(laps.columns) == [c for c in parser.lap_columns if c in laps.columns]


def test_gpx_columns_match_canonical_order():
    parser = ActivityParser()
    records, _, _ = parser.parse(Path(__file__).parent / "files" / "gpx" / "sample.gpx")
    assert list(records.columns) == [c for c in parser.record_columns if c in records.columns]


def test_record_columns_is_mutable_per_instance():
    src = Path(__file__).parent / "files" / "gpx" / "sample.gpx"
    default_parser = ActivityParser()
    custom_parser = ActivityParser()
    custom_parser.record_columns = ["longitude", "latitude"]

    default_records, _, _ = default_parser.parse(src)
    custom_records, _, _ = custom_parser.parse(src)

    assert list(custom_records.columns) == ["longitude", "latitude"]
    assert list(default_records.columns) != ["longitude", "latitude"]


def test_gpx_include_all_columns_appends_namespace_qualified_column():
    src = Path(__file__).parent / "files" / "gpx" / "unknown_extension.gpx"
    records, _, _ = ActivityParser(include_all_columns=True).parse(src)
    assert "{urn:example:unknown-vendor}stress" in records.columns

    records_default, _, _ = ActivityParser().parse(src)
    assert "{urn:example:unknown-vendor}stress" not in records_default.columns


def test_tcx_include_all_columns_appends_collision_columns():
    src = Path(__file__).parent / "files" / "tcx" / "unknown_collision.tcx"
    records, _, _ = ActivityParser(include_all_columns=True).parse(src)
    assert f"{{{TCX_NS}}}value" in records.columns
    assert any(col.startswith(f"{{{TCX_NS}}}VendorB/") for col in records.columns)

    records_default, _, _ = ActivityParser().parse(src)
    assert f"{{{TCX_NS}}}value" not in records_default.columns
