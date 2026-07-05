"""Tests for TCX/GPX parsing against hand-written fixture files."""

import gzip
from pathlib import Path

import pandas as pd
import pytest
from lxml import etree

from activity_parser import ActivityParser
from activity_parser.parse_tcx_gpx import parse_gpx, parse_tcx

FILES = Path(__file__).parent / "files"
SAMPLE_TCX = FILES / "sample.tcx"
SAMPLE_GPX = FILES / "sample.gpx"
NO_POSITION_TCX = FILES / "no_position.tcx"
MULTI_SEGMENT_GPX = FILES / "multi_segment.gpx"
NO_TIME_TCX = FILES / "no_time.tcx"
NO_TIME_GPX = FILES / "no_time.gpx"
MIXED_OFFSET_TCX = FILES / "mixed_offset.tcx"
MIXED_OFFSET_GPX = FILES / "mixed_offset.gpx"
BAD_SPEED_GPX = FILES / "bad_speed.gpx"
GPXTPX_V1_GPX = FILES / "gpxtpx_v1.gpx"
GPXDATA_GPX = FILES / "gpxdata.gpx"
UNKNOWN_EXTENSION_GPX = FILES / "unknown_extension.gpx"
GPX10 = FILES / "gpx10.gpx"
RUNNING_TCX = FILES / "running.tcx"
CADENCE_COLLISION_TCX = FILES / "cadence_collision.tcx"
UNKNOWN_COLLISION_TCX = FILES / "unknown_collision.tcx"
MIXED_CONTENT_TCX = FILES / "mixed_content.tcx"
VENDOR_TYPE_ATTRIBUTE_TCX = FILES / "vendor_type_attribute.tcx"
DUPLICATE_CADENCE_TCX = FILES / "duplicate_cadence.tcx"
LAPS_ONLY_TCX = FILES / "laps_only.tcx"
EXTRA_VENDOR_TYPE_ATTRIBUTE_TCX = FILES / "extra_vendor_type_attribute.tcx"
LX_NAMESPACE_RESET_TCX = FILES / "lx_namespace_reset.tcx"


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
    assert laps["lap_trigger"].tolist() == ["Manual", "Manual"]
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


def test_tcx_extra():
    _, _, extra = ActivityParser().parse(SAMPLE_TCX)
    assert extra["Sport"] == "Biking"
    assert "schemaLocation" not in extra


def test_tcx_extra_type_attribute_only_skipped_for_xsi_namespace():
    # Only genuine xsi:type is schema-validation metadata; a same-named attribute in
    # another namespace is real data and must be kept.
    _, _, extra = ActivityParser().parse(EXTRA_VENDOR_TYPE_ATTRIBUTE_TCX)
    assert extra["type"] == "vendor-real-data"


def test_tcx_without_position():
    records, _, _ = ActivityParser().parse(NO_POSITION_TCX)
    assert list(records.columns) == ["heart_rate", "power"]
    assert records["heart_rate"].tolist() == [100, 101, 102]
    assert records["power"].tolist() == [200, 210, 220]


def test_tcx_no_time_rows_dropped():
    # Trackpoints without a <Time> element get a NaT index; these should be dropped
    # rather than collapsed together as "duplicate" NaT timestamps.
    records, _, _ = ActivityParser().parse(NO_TIME_TCX)
    assert len(records) == 2
    assert records["heart_rate"].tolist() == [100, 101]


def test_tcx_mixed_offset_times():
    # xsd:dateTime allows explicit non-UTC offsets and naive (no-offset) values; all
    # three trackpoints should parse and normalize to UTC rather than raising or being
    # coerced to NaT and dropped.
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
    # CadenceSensor is an attribute of the TPX element itself
    assert records["cadence_sensor"].tolist() == ["Footpod", "Footpod"]
    # LX lap extension fields
    assert laps["avg_cadence"].tolist() == [85]
    assert laps["max_cadence"].tolist() == [90]
    assert laps["total_strides"].tolist() == [300]
    assert laps["avg_power"].tolist() == [250]
    assert laps["max_power"].tolist() == [260]
    assert laps["avg_speed"].tolist() == pytest.approx([10.8])


def test_tcx_base_cadence_beats_run_cadence():
    # Both base Cadence and TPX RunCadence present: base wins (first walked).
    records, _, _ = ActivityParser().parse(CADENCE_COLLISION_TCX)
    assert records["cadence"].tolist() == [80]


def test_tcx_duplicate_element_keeps_both_values():
    # Two literal <Cadence> elements in one Trackpoint: the first claims "cadence", the
    # second is kept under its full-path column rather than being dropped.
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
    # TrainerRoad resets AvgSpeed to no namespace inside a correctly-namespaced LX
    # wrapper; it should still resolve via LX's own namespace.
    _, laps, _ = ActivityParser().parse(LX_NAMESPACE_RESET_TCX)
    assert laps["avg_speed"].tolist() == pytest.approx([28.8])
    assert laps["max_cadence"].tolist() == [95]


def test_tcx_lx_namespace_reset_does_not_overreach():
    # A namespace-reset leaf whose name isn't a real LX field must stay unrecognized,
    # not get matched to something else just because it shares LX's namespace.
    _, low_laps, _ = parse_tcx(LX_NAMESPACE_RESET_TCX)
    assert low_laps["NotARealField"].tolist() == ["99"]


# ---------------------------------------------------------------------------
# GPX
# ---------------------------------------------------------------------------


def test_gpx_records_values():
    records, laps, extra = ActivityParser().parse(SAMPLE_GPX)

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
    # speed is in m/s in the GPX extension, converted to km/h for consistency with FIT
    # and TCX.
    assert records["speed"].tolist() == pytest.approx([18.0, 18.72, 19.44])

    # GPX has no lap information
    assert laps.empty
    assert extra["name"] == "Sample Track"


def test_gpx_multiple_track_segments():
    # Points from all <trkseg> elements are merged into one records frame
    records, _, _ = ActivityParser().parse(MULTI_SEGMENT_GPX)
    assert records["latitude"].tolist() == pytest.approx([37.0, 37.1, 37.2])


def test_gpx_no_time_rows_dropped():
    # Trackpoints without a <time> element get a NaT index; these should be dropped
    # rather than collapsed together as "duplicate" NaT timestamps.
    records, _, _ = ActivityParser().parse(NO_TIME_GPX)
    assert len(records) == 2
    assert records["heart_rate"].tolist() == [100, 101]


def test_gpx_non_numeric_speed_passed_through():
    # One non-numeric speed value means the column skips numeric coercion; the m/s ->
    # km/h conversion must then skip it too (arithmetic on strings raises) and pass the
    # raw values through unchanged.
    records, _, _ = ActivityParser().parse(BAD_SPEED_GPX)
    assert len(records) == 3
    assert records["speed"].tolist() == ["5.0", "n/a", "5.4"]
    # Other columns still coerce and convert normally
    assert records["heart_rate"].tolist() == [100, 101, 102]


def test_gpx_mixed_offset_times():
    # xsd:dateTime allows explicit non-UTC offsets and naive (no-offset) values; all
    # three trackpoints should parse and normalize to UTC rather than raising or being
    # coerced to NaT and dropped.
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
    # Unrecognized columns aren't part of ActivityParser's canonical selector
    normalized, _, _ = ActivityParser().parse(UNKNOWN_EXTENSION_GPX)
    assert column not in normalized.columns


def test_gpx_1_0_base_fields():
    # GPX 1.0 exposes course/speed directly (no <extensions> wrapper). GPS-fix-quality
    # diagnostics (hdop, satellites, fix_type, ...) are schema-known but aren't fitness
    # data, so they're left out of the canonical selector.
    records, _, _ = ActivityParser().parse(GPX10)
    assert records["course"].tolist() == pytest.approx([90.0, 91.0])
    assert records["speed"].tolist() == pytest.approx([18.0, 18.72])
    assert "fix_type" not in records.columns

    normalized, _, _ = ActivityParser().parse(GPX10)
    assert "fix_type" not in normalized.columns


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
    # Truncate mid-document: strict parsing raises, recovery parses the trackpoints that
    # survive
    truncated = tmp_path / "truncated.tcx"
    truncated.write_text(SAMPLE_TCX.read_text()[:2500])

    with pytest.raises(etree.XMLSyntaxError):
        ActivityParser(strict_xml=True).parse(truncated)

    records, _, _ = ActivityParser().parse(truncated)
    assert len(records) >= 1


# ---------------------------------------------------------------------------
# low-level parse_tcx/parse_gpx: unknown-element preservation
# ---------------------------------------------------------------------------


def test_parse_tcx_low_level_matches_high_level_known_columns():
    # parse_tcx already emits canonical names; ActivityParser only narrows/orders them.
    low_records, _, _ = parse_tcx(SAMPLE_TCX)
    high_records, _, _ = ActivityParser().parse(SAMPLE_TCX)
    for col in high_records.columns:
        assert low_records[col].tolist() == high_records[col].tolist()


def test_tcx_unrelated_unknowns_with_same_leaf_name_both_kept():
    # VendorA/value and VendorB/value would collide on the same unknown column if only
    # the leaf name were used; the second must survive under its full path instead.
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
    # Only genuine xsi:type is schema-validation metadata; a same-named attribute in
    # another namespace is real data and must be kept.
    records, _, _ = parse_tcx(VENDOR_TYPE_ATTRIBUTE_TCX)
    assert records["{urn:example:vendor}type"].tolist() == ["vendor-real-data"]
    assert "SomeSchemaType" not in records.iloc[0].tolist()
