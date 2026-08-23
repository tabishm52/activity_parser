"""Tests for FIT parsing against small real-device fixture files."""

import gzip
import io
import struct
from pathlib import Path

import pandas as pd
import pytest
import synthetic_fit

from activity_parser import ActivityParser, FitError
from activity_parser.parse_fit_file import (
    LEFT_RIGHT_BALANCE_PERCENT_MASK,
    LEFT_RIGHT_BALANCE_PERCENT_MASK_100,
    LEFT_RIGHT_BALANCE_RIGHT_FLAG,
    LEFT_RIGHT_BALANCE_RIGHT_FLAG_100,
    add_fractional_columns,
    build_activity,
    coalesce_enhanced_columns,
    normalize_messages,
    parse_fit,
    parse_fit_raw,
    split_left_right_balance,
)

FILES = Path(__file__).parent / "files" / "fit"
EDGE_820 = FILES / "garmin-edge-820-bike.fit"
FENIX_5 = FILES / "garmin-fenix-5-bike.fit"
FENIX_5_RUN = FILES / "garmin-fenix-5-run.fit"
DEVELOPER_DATA = FILES / "DeveloperData.fit"


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


def test_parse_edge_820_activity_values():
    _, _, activity = parse_fit(EDGE_820)
    assert activity.sport == "cycling"
    assert activity.start_time == pd.Timestamp("2017-06-12T16:10:15Z")
    assert activity.total_distance == pytest.approx(0.45712)
    assert activity.total_calories == 8
    assert activity.avg_heart_rate == 116
    assert activity.max_heart_rate == 121
    assert activity.creator == "garmin edge_820"


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
    # total_strokes is FIT's total_cycles field, subfield-resolved for cycling.
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


def split_record_balance(df: pd.DataFrame) -> pd.DataFrame:
    """split_left_right_balance with the per-record (uint8) layout."""
    return split_left_right_balance(
        df,
        right_flag=LEFT_RIGHT_BALANCE_RIGHT_FLAG,
        percent_mask=LEFT_RIGHT_BALANCE_PERCENT_MASK,
        percent_scale=1.0,
    )


def test_split_left_right_balance_decodes_right_flag():
    # 180 = 0x80 | 52: right flag set, 52% -> right leg contributes 52%.
    df = pd.DataFrame({"left_right_balance": [180]})
    out = split_record_balance(df)
    assert out["right_balance"].tolist() == pytest.approx([52.0])
    assert out["left_balance"].tolist() == pytest.approx([48.0])
    assert out["left_right_balance"].tolist() == [180]


def test_split_left_right_balance_decodes_left_flag():
    # 52 = no flag: left leg contributes 52%.
    df = pd.DataFrame({"left_right_balance": [52]})
    out = split_record_balance(df)
    assert out["left_balance"].tolist() == pytest.approx([52.0])
    assert out["right_balance"].tolist() == pytest.approx([48.0])


def test_split_left_right_balance_preserves_missing_values():
    df = pd.DataFrame({"left_right_balance": [180, None]})
    out = split_record_balance(df)
    assert out["right_balance"].iloc[1] != out["right_balance"].iloc[1]  # NaN


def test_split_left_right_balance_noop_without_column():
    df = pd.DataFrame({"cadence": [90.0]})
    out = split_record_balance(df)
    assert "left_balance" not in out.columns
    assert "right_balance" not in out.columns


def test_split_left_right_balance_decodes_enum_quirk_values():
    # The FIT profile renders raw byte 0x80/0x7F as "right"/"mask" strings; confirm
    # both are recovered rather than crashing on cast to float.
    df = pd.DataFrame({"left_right_balance": ["right", "mask", 180]})
    out = split_record_balance(df)
    assert out["right_balance"].tolist() == pytest.approx([0.0, -27.0, 52.0])
    assert out["left_balance"].tolist() == pytest.approx([100.0, 127.0, 48.0])


def test_split_left_right_balance_decodes_enum_quirk_values_100_variant():
    # Same FIT profile issue, but for the lap/session/segment_lap uint16 layout.
    df = pd.DataFrame({"left_right_balance": ["right", "mask", 37968]})
    out = split_left_right_balance(
        df,
        right_flag=LEFT_RIGHT_BALANCE_RIGHT_FLAG_100,
        percent_mask=LEFT_RIGHT_BALANCE_PERCENT_MASK_100,
        percent_scale=100.0,
    )
    assert out["right_balance"].tolist() == pytest.approx([0.0, -63.83, 52.0])
    assert out["left_balance"].tolist() == pytest.approx([100.0, 163.83, 48.0])


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

    with pytest.raises(FitError, match="CRC"):
        ActivityParser(check_crc=True).parse(corrupt)

    records, _, _ = ActivityParser().parse(corrupt)
    assert len(records) == 15


def test_file_like_input():
    with open(EDGE_820, "rb") as f:
        records, _, _ = ActivityParser().parse(f, ext="fit")
    assert len(records) == 15


def test_non_fit_bytes_raise():
    with pytest.raises(FitError, match="not a fit file"):
        parse_fit(io.BytesIO(b"this is not a FIT file"))


@pytest.mark.parametrize(
    "corrupt_bytes",
    [
        pytest.param(b"this is not gzip data at all", id="not_gzipped"),
        pytest.param(
            bytes.fromhex("1f8b08000000000000") + b"not real deflate data" * 5,
            id="corrupt_deflate_stream",
        ),
        pytest.param(gzip.compress(b"x" * 10000)[:20], id="truncated_stream"),
    ],
)
def test_corrupt_gzip_raises(tmp_path, corrupt_bytes):
    corrupt = tmp_path / "corrupt.fit.gz"
    corrupt.write_bytes(corrupt_bytes)

    with pytest.raises(FitError):
        parse_fit(corrupt)


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


# ---------------------------------------------------------------------------
# Guards and seams: synthetic fixtures built by synthetic_fit.py
# ---------------------------------------------------------------------------


def test_parse_fit_drops_duplicate_timestamp_keeping_first():
    records, _, _ = parse_fit(io.BytesIO(synthetic_fit.dup_timestamps()))
    assert records.index.is_unique
    assert records["heart_rate"].tolist() == [100, 101]


def test_parse_fit_drops_record_with_no_timestamp():
    records, _, _ = parse_fit(io.BytesIO(synthetic_fit.missing_timestamp()))
    assert records["heart_rate"].tolist() == [100, 101]


def test_parse_fit_laps_only_fixture():
    records, laps, activity = parse_fit(io.BytesIO(synthetic_fit.laps_only()))
    assert records.empty
    assert isinstance(records.index, pd.DatetimeIndex)
    assert laps["total_distance"].tolist() == pytest.approx([1.0, 1.5])
    assert laps["total_elapsed_time"].tolist() == [150.0, 150.0]
    assert activity.sport == "running"
    assert activity.total_elapsed_time == 300.0
    assert activity.creator == "garmin 1000"


def test_parse_fit_multi_session_uses_first_session_and_file_id():
    # Docstring contract: with more than one session/file_id message, only the first
    # of each is used.
    _, _, activity = parse_fit(io.BytesIO(synthetic_fit.multi_session()))
    assert activity.sport == "running"
    assert activity.total_elapsed_time == 60.0
    assert activity.creator == "garmin 1111"


def test_parse_fit_chained_files(tmp_path):
    # A chained FIT stream is just two FIT sequences back-to-back; parse_fit should
    # merge their records (both fixtures happen to share 2 real-world timestamps,
    # which the usual dedup guard drops) and keep only the first file's
    # session/file_id.
    chained = tmp_path / "chained.fit"
    chained.write_bytes(EDGE_820.read_bytes() + FENIX_5.read_bytes())

    records, _, activity = parse_fit(chained)
    assert len(records) == 15 + 19 - 2
    assert activity.creator == "garmin edge_820"


def test_parse_fit_left_right_balance_end_to_end():
    # parse_fit is the low-level entry point: left_right_balance is kept alongside the
    # decoded columns. ActivityParser's curated column selection is what drops it.
    records, laps, _ = parse_fit(io.BytesIO(synthetic_fit.left_right_balance()))
    assert records["left_balance"].tolist() == pytest.approx([48.0, 52.0])
    assert records["right_balance"].tolist() == pytest.approx([52.0, 48.0])
    assert records["left_right_balance"].tolist() == [180, 52]
    assert laps["left_balance"].tolist() == pytest.approx([48.0])
    assert laps["right_balance"].tolist() == pytest.approx([52.0])
    assert laps["left_right_balance"].tolist() == [37968]


def test_activity_parser_left_right_balance_column_curation():
    src = io.BytesIO(synthetic_fit.left_right_balance())
    curated, _, _ = ActivityParser().parse(src, ext="fit")
    assert "left_right_balance" not in curated.columns

    src.seek(0)
    everything, _, _ = ActivityParser(include_all_columns=True).parse(src, ext="fit")
    assert "left_right_balance" in everything.columns


def test_parse_fit_left_right_balance_enum_quirk_end_to_end():
    # Regression test: this used to crash ~12.7% of a real archive's FIT files.
    records, _, _ = parse_fit(io.BytesIO(synthetic_fit.left_right_balance_enum_quirk()))
    assert records["right_balance"].tolist() == pytest.approx([0.0, -27.0, 52.0])
    assert records["left_balance"].tolist() == pytest.approx([100.0, 127.0, 48.0])


def test_parse_fit_coercion_skips_column_with_non_numeric_value():
    # left_power_phase is an array field: one row has two values (decodes to a
    # tuple), making the column object-dtype and un-coercible as a whole, so it must
    # pass through unchanged while a sibling column with only a genuinely missing
    # value still coerces to float64.
    records, _, _ = parse_fit(io.BytesIO(synthetic_fit.coercion_skip()))
    assert records["left_power_phase"].tolist() == [
        pytest.approx(9.84375),
        (pytest.approx(9.84375), pytest.approx(19.6875)),
        pytest.approx(29.53125),
    ]
    assert records["temperature"].dtype == "float64"
    assert records["temperature"].tolist()[0::2] == pytest.approx([20.0, 21.0])
    assert records["temperature"].isna().tolist() == [False, True, False]


def test_parse_fit_merges_heart_rate_stream():
    records, _, _ = parse_fit(io.BytesIO(synthetic_fit.heart_rate_merge()))
    # First two records fall in the hr stream's coverage (150 bpm); the third has no
    # in-window samples and keeps its device value.
    assert records["heart_rate"].tolist() == [150, 150, 100]


def test_parse_fit_raw_does_not_merge_heart_rate_stream():
    raw = parse_fit_raw(io.BytesIO(synthetic_fit.heart_rate_merge()))
    assert raw["record"]["heart_rate"].tolist() == [100, 100, 100]
    assert len(raw["hr"]) == 2


# ---------------------------------------------------------------------------
# Vendored real-device files: a running activity and a developer-fields sample
# ---------------------------------------------------------------------------


def test_parse_fenix_5_run_activity_values():
    _, _, activity = parse_fit(FENIX_5_RUN)
    assert activity.sport == "running"
    assert activity.creator == "garmin fenix5"


def test_activity_parser_fenix_5_run_canonical_columns():
    records, laps, _ = ActivityParser().parse(FENIX_5_RUN)
    assert records.index.name == "time"
    assert not records.empty
    assert "start_time" in laps.columns
    assert "total_distance" in laps.columns


def test_developer_field_kept_in_raw_parse():
    records, _, activity = parse_fit(DEVELOPER_DATA)
    assert records["doughnuts_earned"].tolist() == [1, 2, 3]
    assert activity.creator == "dynastream 9001"


def test_developer_field_dropped_by_default_kept_with_include_all_columns():
    default_records, _, _ = ActivityParser().parse(DEVELOPER_DATA)
    assert "doughnuts_earned" not in default_records.columns

    all_records, _, _ = ActivityParser(include_all_columns=True).parse(DEVELOPER_DATA)
    assert all_records["doughnuts_earned"].tolist() == [1, 2, 3]


# ---------------------------------------------------------------------------
# normalize_messages: plain dicts, no fixtures
# ---------------------------------------------------------------------------


def test_normalize_messages_strips_field_description_bookkeeping_key():
    messages = {"field_description_mesgs": [{"key": 0, "field_name": "doughnuts_earned"}]}
    assert normalize_messages(messages) == {
        "field_description": [{"field_name": "doughnuts_earned"}]
    }


def test_normalize_messages_renames_unresolved_field_description_field():
    # Same unresolved-field mechanism as record's unknown_61/unknown_66.
    messages = {"field_description_mesgs": [{"key": 0, "field_name": "x", 16: [1, 2]}]}
    assert normalize_messages(messages) == {
        "field_description": [{"field_name": "x", "unknown_16": (1, 2)}]
    }


def test_normalize_messages_developer_field_falls_back_when_field_name_absent():
    # field_name is an optional field_description field, omitted (not None) when a
    # device doesn't populate it.
    messages = {
        "field_description_mesgs": [{"key": 0}],
        "record_mesgs": [{"developer_fields": {0: 5.0}}],
    }
    assert normalize_messages(messages) == {
        "field_description": [{}],
        "record": [{"developer_field_0": 5.0}],
    }


def test_normalize_messages_prefixes_developer_field_colliding_with_known_name():
    # A developer field's name is chosen by whoever wrote the device/app, so nothing
    # stops it from matching a built-in FIT field like "speed".
    messages = {
        "field_description_mesgs": [{"key": 0, "field_name": "speed"}],
        "record_mesgs": [{"timestamp": 1, "developer_fields": {0: 10.0}}],
    }
    assert normalize_messages(messages) == {
        "field_description": [{"field_name": "speed"}],
        "record": [{"timestamp": 1, "developer_speed": 10.0}],
    }


def test_normalize_messages_developer_field_does_not_overwrite_real_field():
    messages = {
        "field_description_mesgs": [{"key": 0, "field_name": "speed"}],
        "record_mesgs": [{"speed": 5.0, "developer_fields": {0: 999.0}}],
    }
    assert normalize_messages(messages) == {
        "field_description": [{"field_name": "speed"}],
        "record": [{"speed": 5.0, "developer_speed": 999.0}],
    }


# ---------------------------------------------------------------------------
# build_activity: plain dicts, no fixtures
# ---------------------------------------------------------------------------


def test_build_activity_prefers_product_name():
    activity = build_activity(
        session=None,
        file_id={"product_name": "Edge 820", "manufacturer": "garmin", "product": 1},
    )
    assert activity.creator == "Edge 820"


def test_build_activity_joins_manufacturer_and_garmin_product():
    file_id = {"manufacturer": "garmin", "garmin_product": 1000}
    activity = build_activity(session=None, file_id=file_id)
    assert activity.creator == "garmin 1000"


def test_build_activity_joins_manufacturer_and_product_fallback():
    activity = build_activity(session=None, file_id={"manufacturer": "wahoo", "product": 42})
    assert activity.creator == "wahoo 42"


def test_build_activity_creator_none_when_no_identifying_fields():
    activity = build_activity(session=None, file_id={"manufacturer": None, "product": None})
    assert activity.creator is None
    activity_empty = build_activity(session=None, file_id={})
    assert activity_empty.creator is None


def test_build_activity_handles_none_session_and_file_id():
    activity = build_activity(session=None, file_id=None)
    assert activity == build_activity(session={}, file_id={})
    assert activity.sport is None
    assert activity.start_time is None
    assert activity.creator is None


def test_build_activity_converts_start_time_to_timestamp():
    activity = build_activity(session={"start_time": "2026-01-05T08:00:00Z"}, file_id=None)
    assert activity.start_time == pd.Timestamp("2026-01-05T08:00:00Z")


def test_build_activity_reads_session_fields():
    activity = build_activity(
        session={
            "sport": "running",
            "total_elapsed_time": 60.0,
            "total_distance": 1.0,
            "total_calories": 5,
            "avg_heart_rate": 90,
            "max_heart_rate": 112,
            "avg_speed": 9.9,
            "max_speed": 13.1,
        },
        file_id=None,
    )
    assert activity.sport == "running"
    assert activity.total_elapsed_time == 60.0
    assert activity.total_distance == 1.0
    assert activity.total_calories == 5
    assert activity.avg_heart_rate == 90
    assert activity.max_heart_rate == 112
    assert activity.avg_speed == 9.9
    assert activity.max_speed == 13.1


# ---------------------------------------------------------------------------
# parse_fit_raw: unprocessed, per-message-type dict of DataFrames
# ---------------------------------------------------------------------------


def test_parse_fit_raw_groups_by_message_type():
    raw = parse_fit_raw(EDGE_820)
    assert len(raw["record"]) == 15
    assert len(raw["lap"]) == 1


def test_parse_fit_raw_omits_absent_message_types():
    raw = parse_fit_raw(io.BytesIO(synthetic_fit.laps_only()))
    assert "record" not in raw
    assert len(raw["file_id"]) == 1
    assert len(raw["session"]) == 1
    assert len(raw["lap"]) == 2


def test_parse_fit_raw_no_records_returns_empty_dict():
    raw = parse_fit_raw(io.BytesIO(empty_fit_bytes()))
    assert raw == {}


def test_parse_fit_raw_keeps_fit_native_units():
    raw = parse_fit_raw(EDGE_820)
    records, _, _ = parse_fit(EDGE_820)
    # Semicircles and meters, against parse_fit's degrees and km for the same file.
    assert raw["record"]["position_lat"].iloc[0] == 446375435
    assert records["latitude"].iloc[0] == pytest.approx(37.414757)
    assert raw["record"]["distance"].iloc[-1] == pytest.approx(457.12)
    assert records["distance"].iloc[-1] == pytest.approx(0.45712)


def test_parse_fit_leaves_developer_fields_unconverted():
    records, _, _ = parse_fit(DEVELOPER_DATA)
    assert records["doughnuts_earned"].iloc[0] == 1
    assert records["speed"].iloc[0] == pytest.approx(170.9568)
