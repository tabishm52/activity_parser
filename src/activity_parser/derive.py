"""Fills an ``Activity``'s missing fields by aggregating its own records/laps."""

import dataclasses
from typing import Literal

import pandas as pd

from .output import Activity


def _aggregate(
    df: pd.DataFrame,
    column: str,
    how: Literal["sum", "mean", "max", "min"],
    *,
    skip_zeros: bool = False,
) -> float | None:
    """A safe aggregation over a numeric column, or None if unavailable."""
    if column not in df.columns or not pd.api.types.is_numeric_dtype(df[column]):
        return None

    values = df[column].dropna()
    if skip_zeros:
        values = values[values != 0]
    if values.empty:
        return None

    return float(getattr(values, how)())


def _range(df: pd.DataFrame, column: str) -> float | None:
    """Max minus min of a numeric column, or None if either is unavailable."""
    high = _aggregate(df, column, "max")
    low = _aggregate(df, column, "min")

    if high is None or low is None:
        return None

    return high - low


def _time_span(records: pd.DataFrame) -> float | None:
    """Seconds between the first and last record, or None with no usable timestamps."""
    if records.empty or not isinstance(records.index, pd.DatetimeIndex):
        return None

    return (records.index.max() - records.index.min()).total_seconds()


def _coalesce(*values: float | None) -> float | None:
    """First non-None value; 0.0 is a value, not a placeholder for "missing"."""
    for value in values:
        if value is not None:
            return value

    return None


def fill_activity(activity: Activity, records: pd.DataFrame, laps: pd.DataFrame) -> Activity:
    """Fills an Activity's missing fields by computing from records and laps.

    A field the file itself reports is never overwritten; this only fills fields the
    file left ``None``. ``total_timer_time``, ``total_ascent`` and ``total_descent`` are
    not derived and are left as the file reported them, ``None`` included.
    """
    # Prefer sum of lap data, fall back to calculating from records
    total_elapsed_time = _coalesce(
        _aggregate(laps, "total_elapsed_time", "sum"), _time_span(records)
    )
    total_distance = _coalesce(
        _aggregate(laps, "total_distance", "sum"), _range(records, "distance")
    )

    # Divides by elapsed time, whereas FIT's avg_speed divides by timer time
    distance = _coalesce(activity.total_distance, total_distance)
    elapsed = _coalesce(activity.total_elapsed_time, total_elapsed_time)
    avg_speed = distance / (elapsed / 3600) if distance is not None and elapsed else None

    derived: dict[str, float | None] = {
        "total_elapsed_time": total_elapsed_time,
        "total_distance": total_distance,
        "total_calories": _aggregate(laps, "total_calories", "sum"),
        "avg_heart_rate": _aggregate(records, "heart_rate", "mean"),
        # Prefer max over records, fall back to max over laps
        "max_heart_rate": _coalesce(
            _aggregate(records, "heart_rate", "max"), _aggregate(laps, "max_heart_rate", "max")
        ),
        "max_speed": _coalesce(
            _aggregate(records, "speed", "max"), _aggregate(laps, "max_speed", "max")
        ),
        "avg_speed": avg_speed,
        # avg_power keeps zero (coasting) samples; avg_cadence drops them (matching FIT)
        "avg_power": _aggregate(records, "power", "mean"),
        "max_power": _coalesce(
            _aggregate(records, "power", "max"), _aggregate(laps, "max_power", "max")
        ),
        "avg_cadence": _aggregate(records, "cadence", "mean", skip_zeros=True),
        "max_cadence": _coalesce(
            _aggregate(records, "cadence", "max"), _aggregate(laps, "max_cadence", "max")
        ),
    }

    to_fill = {
        field: value
        for field, value in derived.items()
        if getattr(activity, field) is None and value is not None
    }

    return dataclasses.replace(activity, **to_fill) if to_fill else activity
