"""Defines the shape of ``parse()``'s return values, shared across FIT/TCX/GPX."""

from dataclasses import dataclass

import pandas as pd

DEFAULT_RECORD_COLUMNS: tuple[str, ...] = (
    "latitude",
    "longitude",
    "altitude",
    "distance",
    "speed",
    "cadence",
    "heart_rate",
    "power",
    "left_balance",
    "right_balance",
    "accumulated_power",
    "temperature",
    "water_temperature",
    "depth",
    "course",
    "bearing",
)

DEFAULT_LAP_COLUMNS: tuple[str, ...] = (
    "start_time",
    "total_elapsed_time",
    "total_timer_time",
    "start_position_lat",
    "start_position_long",
    "end_position_lat",
    "end_position_long",
    "total_distance",
    "total_ascent",
    "total_descent",
    "avg_vam",
    "avg_speed",
    "max_speed",
    "avg_cadence",
    "max_cadence",
    "total_strokes",
    "steps",
    "avg_heart_rate",
    "max_heart_rate",
    "time_in_hr_zone",
    "avg_power",
    "max_power",
    "normalized_power",
    "left_balance",
    "right_balance",
    "time_in_power_zone",
    "total_work",
    "avg_temperature",
    "max_temperature",
    "total_calories",
    "total_fat_calories",
)


@dataclass(frozen=True)
class Activity:
    """File-level summary, present across FIT/TCX/GPX.

    Fields are ``None`` when the source format/file doesn't record them. Values come
    from the file's own summary fields, never computed/derived from records or laps.
    """

    sport: str | None = None
    start_time: pd.Timestamp | None = None
    total_elapsed_time: float | None = None  # seconds
    total_timer_time: float | None = None  # seconds, excludes paused time
    total_distance: float | None = None  # km
    total_ascent: float | None = None  # m
    total_descent: float | None = None  # m
    total_calories: float | None = None  # kcal
    avg_heart_rate: float | None = None  # bpm
    max_heart_rate: float | None = None  # bpm
    avg_power: float | None = None  # W
    max_power: float | None = None  # W
    avg_cadence: float | None = None  # rpm
    max_cadence: float | None = None  # rpm
    avg_speed: float | None = None  # kph
    max_speed: float | None = None  # kph
    creator: str | None = None  # device/app that recorded or wrote the file
    notes: str | None = None
