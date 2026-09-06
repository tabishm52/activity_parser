"""Tests for shared DataFrame/Series refinements used by both TCX/GPX and FIT parsing."""

import pandas as pd
import pytest

from activity_parser.postprocess import coerce_numeric_all_or_nothing, index_by_time


def test_coerces_fully_numeric_column():
    values = pd.Series(["1", "2.5", None])
    out = coerce_numeric_all_or_nothing(values)
    assert out.tolist()[:2] == pytest.approx([1.0, 2.5])
    assert pd.isna(out.iloc[2])


def test_leaves_mixed_column_unchanged():
    values = pd.Series(["1", "n/a", "2.5"])
    out = coerce_numeric_all_or_nothing(values)
    assert out.tolist() == ["1", "n/a", "2.5"]


def test_all_null_column_passed_through():
    values = pd.Series([None, None])
    out = coerce_numeric_all_or_nothing(values)
    assert out.isna().all()


def test_index_by_time_drops_missing_and_duplicate():
    df = pd.DataFrame(
        {
            "time": [pd.Timestamp("2026-01-01"), None, pd.Timestamp("2026-01-01")],
            "value": [1, 2, 3],
        }
    )
    out = index_by_time(df, "time")
    assert out.index.tolist() == [pd.Timestamp("2026-01-01")]
    assert out["value"].tolist() == [1]


def test_index_by_time_missing_column_yields_empty_datetime_index():
    out = index_by_time(pd.DataFrame({"value": []}), "time")
    assert out.empty
    assert isinstance(out.index, pd.DatetimeIndex)


def test_index_by_time_missing_column_and_empty_does_not_mutate_input():
    df = pd.DataFrame({"value": []})
    index_by_time(df, "time")
    assert "time" not in df.columns


def test_index_by_time_missing_column_with_rows_keeps_them():
    df = pd.DataFrame({"value": [1, 2, 3]})
    out = index_by_time(df, "time")
    assert out.index.name == "time"
    assert out["value"].tolist() == [1, 2, 3]
