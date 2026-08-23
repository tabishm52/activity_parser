"""Tests for TCX/GPX parsing against hand-written fixture files."""

import gzip
import io
from pathlib import Path

import pandas as pd
import pytest

from activity_parser import ActivityParser, XmlError
from activity_parser.parse_tcx_gpx import parse_gpx, parse_tcx

FILES = Path(__file__).parent / "files"
TCX_FILES = FILES / "tcx"
GPX_FILES = FILES / "gpx"
SAMPLE_TCX = TCX_FILES / "sample.tcx"
SAMPLE_GPX = GPX_FILES / "sample.gpx"
NO_POSITION_TCX = TCX_FILES / "no_position.tcx"
MULTI_SEGMENT_GPX = GPX_FILES / "multi_segment.gpx"
NO_TIME_TCX = TCX_FILES / "no_time.tcx"
NO_TIME_GPX = GPX_FILES / "no_time.gpx"
ROUTE_NO_TIME_GPX = GPX_FILES / "route_no_time.gpx"
MIXED_OFFSET_TCX = TCX_FILES / "mixed_offset.tcx"
MIXED_OFFSET_GPX = GPX_FILES / "mixed_offset.gpx"
BAD_SPEED_GPX = GPX_FILES / "bad_speed.gpx"
GPXTPX_V1_GPX = GPX_FILES / "gpxtpx_v1.gpx"
GPXDATA_GPX = GPX_FILES / "gpxdata.gpx"
UNKNOWN_EXTENSION_GPX = GPX_FILES / "unknown_extension.gpx"
GPX10 = GPX_FILES / "gpx10.gpx"
RUNNING_TCX = TCX_FILES / "running.tcx"
CADENCE_COLLISION_TCX = TCX_FILES / "cadence_collision.tcx"
UNKNOWN_COLLISION_TCX = TCX_FILES / "unknown_collision.tcx"
MIXED_CONTENT_TCX = TCX_FILES / "mixed_content.tcx"
VENDOR_TYPE_ATTRIBUTE_TCX = TCX_FILES / "vendor_type_attribute.tcx"
DUPLICATE_CADENCE_TCX = TCX_FILES / "duplicate_cadence.tcx"
LAPS_ONLY_TCX = TCX_FILES / "laps_only.tcx"
ACTIVITY_METADATA_TCX = TCX_FILES / "activity_metadata.tcx"
LX_NAMESPACE_RESET_TCX = TCX_FILES / "lx_namespace_reset.tcx"
METADATA_GPX = GPX_FILES / "metadata.gpx"


# ---------------------------------------------------------------------------
# TCX
# ---------------------------------------------------------------------------


def test_tcx_records_values():
    records, _, _ = ActivityParser().parse(SAMPLE_TCX)

    assert records.index.name == "time"
    assert isinstance(records.index, pd.DatetimeIndex)
    # Duplicate timestamp dropped: 6 trackpoints -> 5 rows, first kept
    assert len(records) == 5
    assert (records["heart_rate"] != 999).all()

    assert records["latitude"].tolist() == pytest.approx(
        [37.0000, 37.0001, 37.0002, 37.0003, 37.0004]
    )
    assert records["longitude"].iloc[0] == pytest.approx(-122.0)
    assert records["altitude"].tolist() == [10.0, 11.0, 12.0, 13.0, 14.0]
    # DistanceMeters converted to km
    assert records["distance"].tolist() == pytest.approx([0.0, 0.01, 0.02, 0.03, 0.04])
    # Speed converted from m/s to km/h
    assert (records["speed"] == 36.0).all()
    # Value-wrapped HeartRateBpm extracted
    assert records["heart_rate"].tolist() == [100, 101, 102, 103, 104]
    assert records["cadence"].tolist() == [80, 81, 82, 83, 84]
    assert records["power"].tolist() == [200, 210, 220, 230, 240]


def test_tcx_laps():
    _, laps, _ = ActivityParser().parse(SAMPLE_TCX)

    assert len(laps) == 2
    assert laps["total_elapsed_time"].dtype == "float64"
    assert laps["total_elapsed_time"].tolist() == [3.0, 2.0]
    # DistanceMeters converted to km
    assert laps["total_distance"].tolist() == pytest.approx([0.02, 0.02])
    # MaximumSpeed converted from m/s to km/h
    assert laps["max_speed"].tolist() == pytest.approx([43.2, 43.2])
    assert laps["avg_heart_rate"].tolist() == [101, 103]
    assert laps["max_heart_rate"].tolist() == [102, 104]
    assert laps["total_calories"].tolist() == [10, 7]
    assert pd.api.types.is_datetime64_any_dtype(laps["start_time"])


def test_tcx_activity():
    _, _, activity = ActivityParser().parse(SAMPLE_TCX)
    assert activity.sport == "Biking"
    assert activity.start_time == pd.Timestamp("2026-01-05T08:00:00Z")


def test_tcx_activity_creator_and_notes():
    _, _, activity = ActivityParser().parse(ACTIVITY_METADATA_TCX)
    assert activity.sport == "Running"
    assert activity.creator == "Garmin Forerunner 945"
    assert activity.notes == "Morning run"


def test_tcx_without_position():
    records, _, _ = ActivityParser().parse(NO_POSITION_TCX)
    assert list(records.columns) == ["heart_rate", "power"]
    assert records["heart_rate"].tolist() == [100, 101, 102]
    assert records["power"].tolist() == [200, 210, 220]


def test_tcx_no_time_rows_dropped():
    # NaT rows (missing <Time>) are dropped individually, not merged as duplicates.
    records, _, _ = ActivityParser().parse(NO_TIME_TCX)
    assert len(records) == 2
    assert records["heart_rate"].tolist() == [100, 101]


def test_tcx_mixed_offset_times():
    # xsd:dateTime allows naive and non-UTC-offset values; both should parse to UTC.
    records, _, _ = ActivityParser().parse(MIXED_OFFSET_TCX)
    assert len(records) == 3
    index = records.index
    assert isinstance(index, pd.DatetimeIndex)
    assert index.tz is not None
    assert index.tolist() == [
        pd.Timestamp("2026-03-08T09:59:59Z"),
        pd.Timestamp("2026-03-08T10:00:00Z"),
        pd.Timestamp("2026-03-08T04:00:00Z"),
    ]
    assert records["heart_rate"].tolist() == [100, 101, 102]


def test_tcx_run_cadence_extension():
    # No base <Cadence> element; ActivityExtension's TPX/RunCadence populates cadence.
    records, laps, _ = ActivityParser().parse(RUNNING_TCX)
    assert records["cadence"].tolist() == [85, 86]
    assert records["power"].tolist() == [250, 255]
    assert records["speed"].tolist() == pytest.approx([10.8, 10.8])
    assert laps["avg_cadence"].tolist() == [85]
    assert laps["max_cadence"].tolist() == [90]
    assert laps["steps"].tolist() == [300]
    assert laps["avg_power"].tolist() == [250]
    assert laps["max_power"].tolist() == [260]
    assert laps["avg_speed"].tolist() == pytest.approx([10.8])


def test_tcx_base_cadence_beats_run_cadence():
    # Both base Cadence and TPX RunCadence present: base wins (first walked).
    records, _, _ = ActivityParser().parse(CADENCE_COLLISION_TCX)
    assert records["cadence"].tolist() == [80]


def test_tcx_duplicate_element_keeps_both_values():
    # Two <Cadence> elements: first claims "cadence", second keeps its full path.
    records, _, _ = ActivityParser().parse(DUPLICATE_CADENCE_TCX)
    assert records["cadence"].tolist() == [80]
    low_records, _, _ = parse_tcx(DUPLICATE_CADENCE_TCX)
    ns = "http://www.garmin.com/xmlschemas/TrainingCenterDatabase/v2"
    assert low_records[f"{{{ns}}}Cadence"].tolist() == ["81"]


def test_tcx_laps_only_file_has_empty_records():
    # A manually-logged workout: lap summary data but no trackpoints at all.
    records, laps, _ = ActivityParser().parse(LAPS_ONLY_TCX)
    assert records.empty
    assert isinstance(records.index, pd.DatetimeIndex)
    assert laps["total_distance"].tolist() == pytest.approx([5.0])


def test_tcx_lx_namespace_reset_still_resolves():
    # TrainerRoad resets AvgSpeed to no namespace; it must still resolve via LX.
    _, laps, _ = ActivityParser().parse(LX_NAMESPACE_RESET_TCX)
    assert laps["avg_speed"].tolist() == pytest.approx([28.8])
    assert laps["max_cadence"].tolist() == [95]


def test_tcx_lx_namespace_reset_does_not_overreach():
    # A reset-namespace leaf that isn't a real LX field must stay unrecognized.
    _, low_laps, _ = parse_tcx(LX_NAMESPACE_RESET_TCX)
    assert low_laps["NotARealField"].tolist() == ["99"]


# ---------------------------------------------------------------------------
# GPX
# ---------------------------------------------------------------------------


def test_gpx_records_values():
    records, laps, _ = ActivityParser().parse(SAMPLE_GPX)

    assert records.index.name == "time"
    # Duplicate timestamp dropped: 4 trkpt -> 3 rows, first kept
    assert len(records) == 3
    assert (records["heart_rate"] != 999).all()

    assert records["latitude"].tolist() == pytest.approx([37.0000, 37.0001, 37.0002])
    assert records["altitude"].tolist() == [10.0, 11.0, 12.0]
    assert records["heart_rate"].tolist() == [100, 101, 102]
    assert records["cadence"].tolist() == [80, 81, 82]
    assert records["power"].tolist() == [200, 210, 220]
    assert (records["temperature"] == 19).all()
    # speed (m/s in the GPX extension) converts to km/h, like FIT and TCX.
    assert records["speed"].tolist() == pytest.approx([18.0, 18.72, 19.44])
    assert laps.empty


def test_gpx_activity():
    _, _, activity = ActivityParser().parse(SAMPLE_GPX)
    assert activity.creator == "activity_parser tests"
    assert activity.start_time == pd.Timestamp("2026-01-05T08:00:00Z")


def test_gpx_activity_desc():
    _, _, activity = ActivityParser().parse(METADATA_GPX)
    assert activity.creator == "Garmin Connect"
    assert activity.notes == "Evening ride"


def test_gpx_multiple_track_segments():
    # Points from all <trkseg> elements are merged into one records frame
    records, _, _ = ActivityParser().parse(MULTI_SEGMENT_GPX)
    assert records["latitude"].tolist() == pytest.approx([37.0, 37.1, 37.2])


def test_gpx_no_time_rows_dropped():
    # NaT rows (missing <time>) are dropped individually, not merged as duplicates.
    records, _, _ = ActivityParser().parse(NO_TIME_GPX)
    assert len(records) == 2
    assert records["heart_rate"].tolist() == [100, 101]


def test_gpx_route_with_no_time_anywhere_keeps_all_rows():
    # Legal per GPX schema: a route with no <time> anywhere keeps all its points.
    records, _, _ = ActivityParser().parse(ROUTE_NO_TIME_GPX)
    assert len(records) == 3
    assert records["altitude"].tolist() == pytest.approx([10.0, 11.0, 12.0])


def test_gpx_non_numeric_speed_passed_through():
    # A non-numeric speed skips coercion; unit conversion then skips it too, unchanged.
    records, _, _ = ActivityParser().parse(BAD_SPEED_GPX)
    assert len(records) == 3
    assert records["speed"].tolist() == ["5.0", "n/a", "5.4"]
    # Other columns still coerce and convert normally
    assert records["heart_rate"].tolist() == [100, 101, 102]


def test_gpx_mixed_offset_times():
    # xsd:dateTime allows naive and non-UTC-offset values; both should parse to UTC.
    records, _, _ = ActivityParser().parse(MIXED_OFFSET_GPX)
    assert len(records) == 3
    index = records.index
    assert isinstance(index, pd.DatetimeIndex)
    assert index.tz is not None
    assert index.tolist() == [
        pd.Timestamp("2026-03-08T09:59:59Z"),
        pd.Timestamp("2026-03-08T10:00:00Z"),
        pd.Timestamp("2026-03-08T04:00:00Z"),
    ]
    assert records["heart_rate"].tolist() == [100, 101, 102]


def test_gpx_track_point_extension_v1():
    # v1 has no speed/course/bearing, unlike v2.
    records, _, _ = ActivityParser().parse(GPXTPX_V1_GPX)
    assert records["heart_rate"].tolist() == [100, 101]
    assert records["cadence"].tolist() == [80, 81]
    assert records["temperature"].tolist() == [18, 18]
    assert records["water_temperature"].tolist() == [15, 15]
    assert records["depth"].tolist() == pytest.approx([2.0, 2.1])
    assert "speed" not in records.columns


def test_gpx_cluetrust_gpxdata_extension():
    records, _, _ = ActivityParser().parse(GPXDATA_GPX)
    assert records["heart_rate"].tolist() == [100, 101]
    assert records["cadence"].tolist() == [80, 81]
    assert records["temperature"].tolist() == [19, 19]
    assert records["distance"].tolist() == pytest.approx([0.0, 0.01])


def test_gpx_unknown_extension_kept_as_namespaced_string():
    records, _, _ = parse_gpx(UNKNOWN_EXTENSION_GPX)
    column = "{urn:example:unknown-vendor}stress"
    assert records[column].tolist() == ["42", "43"]
    # Unrecognized columns aren't part of ActivityParser's default record_columns
    normalized, _, _ = ActivityParser().parse(UNKNOWN_EXTENSION_GPX)
    assert column not in normalized.columns


def test_gpx_1_0_base_fields():
    # GPX 1.0 exposes course/speed directly; GPS-fix diagnostics aren't fitness data.
    records, _, _ = ActivityParser().parse(GPX10)
    assert records.index.name == "time"
    assert records.index.tolist() == [
        pd.Timestamp("2026-01-05T08:00:00Z"),
        pd.Timestamp("2026-01-05T08:00:01Z"),
    ]
    assert records["latitude"].tolist() == pytest.approx([37.0000, 37.0001])
    assert records["longitude"].tolist() == pytest.approx([-122.0000, -122.0001])
    assert records["altitude"].tolist() == pytest.approx([10.0, 11.0])
    assert records["course"].tolist() == pytest.approx([90.0, 91.0])
    assert records["speed"].tolist() == pytest.approx([18.0, 18.72])
    assert "fix_type" not in records.columns


# ---------------------------------------------------------------------------
# gz handling and XML recovery
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("path", [SAMPLE_TCX, SAMPLE_GPX], ids=["tcx", "gpx"])
def test_gz_round_trip(path, tmp_path):
    gz_path = tmp_path / (path.name + ".gz")
    gz_path.write_bytes(gzip.compress(path.read_bytes()))

    plain, _, _ = ActivityParser().parse(path)
    unzipped, _, _ = ActivityParser().parse(gz_path)
    pd.testing.assert_frame_equal(plain, unzipped)


def test_malformed_xml_recovery(tmp_path):
    # Truncate mid-document: strict parsing raises, recovery parses the survivors
    truncated = tmp_path / "truncated.tcx"
    truncated.write_text(SAMPLE_TCX.read_text()[:2500])

    with pytest.raises(XmlError):
        ActivityParser(strict_xml=True).parse(truncated)

    records, _, _ = ActivityParser().parse(truncated)
    assert len(records) >= 1


def test_non_xml_bytes_raise():
    with pytest.raises(XmlError, match="No parseable XML content"):
        parse_tcx(io.BytesIO(b"this is not xml at all, just some prose."))


def test_empty_bytes_raise_even_without_strict_xml():
    with pytest.raises(XmlError, match="Document is empty"):
        parse_tcx(io.BytesIO(b""))


# ---------------------------------------------------------------------------
# low-level parse_tcx/parse_gpx: unknown-element preservation
# ---------------------------------------------------------------------------


def test_tcx_laps_do_not_leak_trackpoint_columns():
    _, laps, _ = parse_tcx(SAMPLE_TCX)
    assert not any("Trackpoint" in col for col in laps.columns)


def test_parse_tcx_low_level_matches_high_level_known_columns():
    # parse_tcx already emits canonical names; ActivityParser only narrows/orders them.
    low_records, _, _ = parse_tcx(SAMPLE_TCX)
    high_records, _, _ = ActivityParser().parse(SAMPLE_TCX)
    for col in high_records.columns:
        assert low_records[col].tolist() == high_records[col].tolist()


def test_tcx_unrelated_unknowns_with_same_leaf_name_both_kept():
    # VendorA/value and VendorB/value collide on leaf name alone; both must survive.
    records, _, _ = parse_tcx(UNKNOWN_COLLISION_TCX)
    ns = "http://www.garmin.com/xmlschemas/TrainingCenterDatabase/v2"
    assert records[f"{{{ns}}}value"].tolist() == ["111"]
    assert records[f"{{{ns}}}VendorB/{{{ns}}}value"].tolist() == ["222"]


def test_tcx_mixed_content_keeps_both_text_and_child():
    # An element with both leaf text and a child element used to only keep the text.
    records, _, _ = parse_tcx(MIXED_CONTENT_TCX)
    ns = "http://www.garmin.com/xmlschemas/TrainingCenterDatabase/v2"
    assert records[f"{{{ns}}}Weird"].tolist() == ["leaf-text-here"]
    assert records[f"{{{ns}}}Nested"].tolist() == ["should-not-be-lost"]


def test_tcx_type_attribute_only_skipped_for_xsi_namespace():
    # Only genuine xsi:type is metadata; a same-named attribute elsewhere is real data.
    records, _, _ = parse_tcx(VENDOR_TYPE_ATTRIBUTE_TCX)
    assert records["{urn:example:vendor}type"].tolist() == ["vendor-real-data"]
    assert "SomeSchemaType" not in records.iloc[0].tolist()
