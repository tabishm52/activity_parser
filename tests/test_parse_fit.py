"""Tests for FIT parsing against small real-device fixture files."""

import gzip
import io
import struct
from pathlib import Path

import fitdecode
import pandas as pd
import pytest

from activity_parser import ActivityParser
from activity_parser.parse_fit_file import (
    add_fractional_columns,
    coalesce_enhanced_columns,
    parse_fit,
    split_left_right_balance,
)

FILES = Path(__file__).parent / "files" / "fit"
EDGE_820 = FILES / "garmin-edge-820-bike.fit"
FENIX_5 = FILES / "garmin-fenix-5-bike.fit"


def empty_fit_bytes() -> bytes:
    """Builds the smallest valid FIT stream: a 12-byte header and CRC footer, no
    data messages. check_crc=False (the parse_fit default) skips CRC verification,
    so the footer value itself is irrelevant.
    """
    header = struct.pack("<2BHI4s", 12, 0x10, 100, 0, b".FIT")
    return header + struct.pack("<H", 0)


@pytest.mark.parametrize("path", [EDGE_820, FENIX_5], ids=lambda p: p.stem)
def test_parse_fit_records_index(path):
    records, laps, activity = parse_fit(path)
    assert records.index.name == "timestamp"
    assert isinstance(records.index, pd.DatetimeIndex)
    assert records.index.is_unique
    assert not records.index.hasnans
    assert len(laps) == 1
    assert activity.sport is not None
    assert activity.creator is not None


def test_parse_fit_keeps_unknown_record_fields():
    records, _, _ = parse_fit(EDGE_820)
    assert "unknown_61" in records.columns
    assert "unknown_66" in records.columns


def test_activity_parser_drops_unknown_fields_from_canonical_output():
    records, laps, _ = ActivityParser().parse(EDGE_820)
    assert not any(col.startswith("unknown_") for col in records.columns)
    assert not any(col.startswith("unknown_") for col in laps.columns)


@pytest.mark.parametrize("path", [EDGE_820, FENIX_5], ids=lambda p: p.stem)
def test_parse_fit_numeric_dtypes(path):
    records, _, _ = parse_fit(path)
    for col in ("latitude", "longitude", "distance", "speed"):
        assert records[col].dtype == "float64", col


def test_parse_edge_820_values():
    records, _, _ = parse_fit(EDGE_820)
    assert len(records) == 15
    assert records["latitude"].iloc[0] == pytest.approx(37.414757)
    assert records["longitude"].iloc[0] == pytest.approx(-122.068886)
    assert records["heart_rate"].iloc[0] == 101
    assert records["distance"].iloc[-1] == pytest.approx(0.45712)


def test_parse_fit_renames_position_to_lat_long():
    records, _, _ = parse_fit(EDGE_820)
    assert "latitude" in records.columns
    assert "longitude" in records.columns
    assert "position_lat" not in records.columns
    assert "position_long" not in records.columns


def test_parse_fit_coalesces_enhanced_columns():
    records, laps, _ = parse_fit(EDGE_820)
    assert (records["altitude"] == records["enhanced_altitude"]).all()
    assert (laps["avg_speed"] == laps["enhanced_avg_speed"]).all()
    assert (laps["max_speed"] == laps["enhanced_max_speed"]).all()


def test_parse_fit_combines_fractional_cadence():
    _, laps, _ = parse_fit(EDGE_820)
    assert laps["avg_cadence"].iloc[0] == pytest.approx(68.320312)
    assert laps["max_cadence"].iloc[0] == pytest.approx(71.0)


def test_parse_fenix_5_values():
    records, _, _ = parse_fit(FENIX_5)
    assert len(records) == 19
    assert records["heart_rate"].iloc[0] == 77
    assert records["distance"].iloc[-1] == pytest.approx(0.45952)


def test_activity_parser_canonical_columns():
    records, laps, _ = ActivityParser().parse(EDGE_820)
    assert records.index.name == "time"
    assert list(records.columns) == [
        "latitude",
        "longitude",
        "altitude",
        "distance",
        "speed",
        "cadence",
        "heart_rate",
        "temperature",
    ]
    assert "start_time" in laps.columns
    assert "total_distance" in laps.columns


def test_activity_parser_keeps_total_strokes():
    # FIT's total_cycles field resolves dynamically to total_strokes (cycling) or
    # total_strides (running) via fitdecode's subfield mechanism; total_strokes is a
    # real, populated field for bike activities, distinct from the unrelated
    # stroke_count field (which never appears in these fixtures).
    _, laps, _ = ActivityParser().parse(EDGE_820)
    assert laps["total_strokes"].tolist() == [75]


def test_activity_parser_matches_parse_fit():
    raw, _, _ = parse_fit(EDGE_820)
    canonical, _, _ = ActivityParser().parse(EDGE_820)
    pd.testing.assert_series_equal(
        canonical["latitude"],
        raw["latitude"],
        check_names=False,
    )


def test_activity_parser_include_all_columns_appends_unknown_fit_fields():
    parser = ActivityParser(include_all_columns=True)
    records, _, _ = parser.parse(EDGE_820)
    record_columns_present = [c for c in parser.record_columns if c in records.columns]
    assert list(records.columns[: len(record_columns_present)]) == record_columns_present
    assert "unknown_61" in records.columns
    assert "unknown_66" in records.columns
    assert list(records.columns).index("unknown_61") >= len(record_columns_present)


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


def test_add_fractional_columns_sums_both_present():
    df = pd.DataFrame({"cadence": [90.0, 85.0], "fractional_cadence": [0.5, 0.25]})
    out = add_fractional_columns(df, {"cadence": "fractional_cadence"})
    assert out["cadence"].tolist() == pytest.approx([90.5, 85.25])


def test_add_fractional_columns_treats_missing_fractional_value_as_zero():
    df = pd.DataFrame({"cadence": [90.0, 85.0], "fractional_cadence": [0.5, None]})
    out = add_fractional_columns(df, {"cadence": "fractional_cadence"})
    assert out["cadence"].tolist() == pytest.approx([90.5, 85.0])


def test_add_fractional_columns_fills_missing_base_column():
    df = pd.DataFrame({"fractional_cadence": [0.5, 0.25]})
    out = add_fractional_columns(df, {"cadence": "fractional_cadence"})
    assert out["cadence"].tolist() == pytest.approx([0.5, 0.25])


def test_add_fractional_columns_noop_without_fractional_column():
    df = pd.DataFrame({"cadence": [90.0, 85.0]})
    out = add_fractional_columns(df, {"cadence": "fractional_cadence"})
    assert out["cadence"].tolist() == [90.0, 85.0]
    assert "fractional_cadence" not in out.columns


def test_split_left_right_balance_decodes_right_flag():
    # 180 = 0x80 | 52: right flag set, 52% -> right leg contributes 52%.
    df = pd.DataFrame({"left_right_balance": [180]})
    out = split_left_right_balance(df)
    assert out["right_balance"].tolist() == pytest.approx([52.0])
    assert out["left_balance"].tolist() == pytest.approx([48.0])
    assert "left_right_balance" not in out.columns


def test_split_left_right_balance_decodes_left_flag():
    # 52 = no flag: left leg contributes 52%.
    df = pd.DataFrame({"left_right_balance": [52]})
    out = split_left_right_balance(df)
    assert out["left_balance"].tolist() == pytest.approx([52.0])
    assert out["right_balance"].tolist() == pytest.approx([48.0])


def test_split_left_right_balance_preserves_missing_values():
    df = pd.DataFrame({"left_right_balance": [180, None]})
    out = split_left_right_balance(df)
    assert out["right_balance"].iloc[1] != out["right_balance"].iloc[1]  # NaN


def test_split_left_right_balance_noop_without_column():
    df = pd.DataFrame({"cadence": [90.0]})
    out = split_left_right_balance(df)
    assert "left_balance" not in out.columns
    assert "right_balance" not in out.columns


def test_gz_round_trip(tmp_path):
    gz_path = tmp_path / (EDGE_820.name + ".gz")
    gz_path.write_bytes(gzip.compress(EDGE_820.read_bytes()))

    plain, _, _ = ActivityParser().parse(EDGE_820)
    unzipped, _, _ = ActivityParser().parse(gz_path)
    pd.testing.assert_frame_equal(plain, unzipped)


def test_crc_mismatch_recovery(tmp_path):
    # Flip the last byte of the file's CRC footer: check_crc=True raises, the
    # default (False) skips verification and parses the file anyway.
    corrupt = tmp_path / "corrupt_crc.fit"
    data = bytearray(EDGE_820.read_bytes())
    data[-1] ^= 0xFF
    corrupt.write_bytes(data)

    with pytest.raises(fitdecode.FitCRCError):
        ActivityParser(check_crc=True).parse(corrupt)

    records, _, _ = ActivityParser().parse(corrupt)
    assert len(records) == 15


def test_file_like_input():
    with open(EDGE_820, "rb") as f:
        records, _, _ = ActivityParser().parse(f, ext="fit")
    assert len(records) == 15


def test_non_fit_bytes_raise():
    with pytest.raises(fitdecode.FitHeaderError):
        parse_fit(io.BytesIO(b"this is not a FIT file"))


def test_parse_fit_no_records_yields_empty_datetime_index():
    # No record messages at all (e.g. a manually-logged workout): records should be
    # empty with a DatetimeIndex, matching TCX/GPX's laps-only behavior, rather than
    # falling back to a RangeIndex.
    records, laps, activity = parse_fit(io.BytesIO(empty_fit_bytes()))
    assert records.empty
    assert records.index.name == "timestamp"
    assert isinstance(records.index, pd.DatetimeIndex)
    assert laps.empty
    assert activity.sport is None
