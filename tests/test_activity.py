"""Tests for filling an Activity's missing fields from its own records/laps."""

from pathlib import Path

import pandas as pd

from activity_parser.activity import Activity, fill_activity
from activity_parser.parse_tcx_gpx import parse_tcx

FILES = Path(__file__).parent / "files"
ZERO_SAMPLES_TCX = FILES / "tcx" / "zero_samples.tcx"


def test_avg_power_keeps_zero_samples_avg_cadence_drops_them():
    _, _, activity = parse_tcx(ZERO_SAMPLES_TCX)
    assert activity.avg_power == 105.0
    assert activity.avg_cadence == 82.0


def test_fill_activity_ignores_lap_level_sensor_summaries():
    # A lap sensor summary can silently be 0 when unpaired; only records are trusted.
    laps = pd.DataFrame({"max_heart_rate": [150.0, 160.0], "max_speed": [30.0, 25.0]})
    result = fill_activity(Activity(), pd.DataFrame(), laps)
    assert result.max_heart_rate is None
    assert result.max_speed is None


def test_fill_activity_all_missing_column_sums_to_none_not_zero():
    laps = pd.DataFrame({"total_calories": [float("nan"), float("nan")]})
    result = fill_activity(Activity(), pd.DataFrame(), laps)
    assert result.total_calories is None


def test_fill_activity_never_overwrites_a_reported_field():
    reported = Activity(total_distance=1.0)
    laps = pd.DataFrame({"total_distance": [5.0]})
    result = fill_activity(reported, pd.DataFrame(), laps)
    assert result.total_distance == 1.0


def test_fill_activity_returns_input_unchanged_when_nothing_is_derivable():
    activity = Activity()
    result = fill_activity(activity, pd.DataFrame(), pd.DataFrame())
    assert result == activity


def test_fill_activity_avg_speed_guards_against_zero_elapsed_time():
    activity = Activity(total_distance=5.0, total_elapsed_time=0.0)
    result = fill_activity(activity, pd.DataFrame(), pd.DataFrame())
    assert result.avg_speed is None


def test_fill_activity_prefers_a_reported_zero_over_a_nonzero_fallback():
    laps = pd.DataFrame({"total_distance": [0.0]})
    records = pd.DataFrame({"distance": [5.0, 10.0]})
    result = fill_activity(Activity(), records, laps)
    assert result.total_distance == 0.0


def test_fill_activity_ignores_non_numeric_columns():
    records = pd.DataFrame({"heart_rate": ["n/a"], "power": ["n/a"]})
    laps = pd.DataFrame({"total_calories": ["n/a"]})
    result = fill_activity(Activity(), records, laps)
    assert result.avg_heart_rate is None
    assert result.avg_power is None
    assert result.total_calories is None
