"""Tests for FIT parsing against small real-device fixture files."""

import gzip
import io
from pathlib import Path

import fitdecode
import pandas as pd
import pytest

from activity_parser import ActivityParser
from activity_parser.parse_fit_file import parse_fit

FILES = Path(__file__).parent / "files"
EDGE_820 = FILES / "garmin-edge-820-bike.fit"
FENIX_5 = FILES / "garmin-fenix-5-bike.fit"


@pytest.mark.parametrize("path", [EDGE_820, FENIX_5], ids=lambda p: p.stem)
def test_parse_fit_records_index(path):
    records, laps, extra = parse_fit(path)
    assert records.index.name == "timestamp"
    assert isinstance(records.index, pd.DatetimeIndex)
    assert records.index.is_unique
    assert not records.index.hasnans
    assert len(laps) == 1
    assert "session" in extra
    assert "file_id" in extra


@pytest.mark.parametrize("path", [EDGE_820, FENIX_5], ids=lambda p: p.stem)
def test_parse_fit_numeric_dtypes(path):
    records, _, _ = parse_fit(path)
    for col in ("position_lat", "position_long", "distance", "speed"):
        assert records[col].dtype == "float64", col


def test_parse_edge_820_values():
    records, _, _ = parse_fit(EDGE_820)
    assert len(records) == 15
    assert records["position_lat"].iloc[0] == pytest.approx(37.414757)
    assert records["position_long"].iloc[0] == pytest.approx(-122.068886)
    assert records["heart_rate"].iloc[0] == 101
    assert records["distance"].iloc[-1] == pytest.approx(0.45712)


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
        "fractional_cadence",
        "heart_rate",
        "temperature",
    ]
    assert "start_time" in laps.columns
    assert "total_distance" in laps.columns


def test_activity_parser_matches_parse_fit():
    raw, _, _ = parse_fit(EDGE_820)
    canonical, _, _ = ActivityParser().parse(EDGE_820)
    pd.testing.assert_series_equal(
        canonical["latitude"],
        raw["position_lat"],
        check_names=False,
    )


def test_gz_round_trip(tmp_path):
    gz_path = tmp_path / (EDGE_820.name + ".gz")
    gz_path.write_bytes(gzip.compress(EDGE_820.read_bytes()))

    plain, _, _ = ActivityParser().parse(EDGE_820)
    unzipped, _, _ = ActivityParser().parse(gz_path)
    pd.testing.assert_frame_equal(plain, unzipped)


def test_file_like_input():
    with open(EDGE_820, "rb") as f:
        records, _, _ = ActivityParser().parse(f, ext="fit")
    assert len(records) == 15


def test_non_fit_bytes_raise():
    with pytest.raises(fitdecode.FitHeaderError):
        parse_fit(io.BytesIO(b"this is not a FIT file"))
