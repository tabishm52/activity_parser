"""Tests for TCX/GPX parsing against hand-written fixture files."""

import gzip
from pathlib import Path

import pandas as pd
import pytest
from lxml import etree

from activity_parser import ActivityParser
from activity_parser.parse_tcx_gpx import should_coerce_numeric

FILES = Path(__file__).parent / "files"
SAMPLE_TCX = FILES / "sample.tcx"
SAMPLE_GPX = FILES / "sample.gpx"
NO_POSITION_TCX = FILES / "no_position.tcx"
MULTI_SEGMENT_GPX = FILES / "multi_segment.gpx"
NO_TIME_TCX = FILES / "no_time.tcx"
NO_TIME_GPX = FILES / "no_time.gpx"
MIXED_OFFSET_TCX = FILES / "mixed_offset.tcx"
MIXED_OFFSET_GPX = FILES / "mixed_offset.gpx"


def test_should_coerce_numeric():
    assert should_coerce_numeric("lat")
    assert should_coerce_numeric("HeartRateBpm")
    assert should_coerce_numeric("MaximumSpeed")  # substring match
    assert not should_coerce_numeric("Time")
    assert not should_coerce_numeric("Notes")


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
