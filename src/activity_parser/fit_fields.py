"""Unit conversions applied to known FIT fields, and the tables driving them.

FIT stores positions in semicircles, distances in meters and speeds in m/s. This
package normalizes those to degrees, km and km/h. Vertical rates (``avg_vam``,
``vertical_speed``, ...) are left in m/s.

The tables are generated from the FIT profile in garmin-fit-sdk 21.212.0, covering
the ``record``, ``lap`` and ``session`` message types. ``tests/test_fit_fields.py``
regenerates them and fails if they drift from the installed profile.
"""

from collections.abc import Mapping
from typing import Any

import pandas as pd

from .postprocess import coerce_numeric_all_or_nothing

SEMICIRCLES_TO_DEGREES = 180.0 / 2**31
M_TO_KM = 1 / 1000
MPS_TO_KMH = 3.6

RECORD_UNITS: dict[str, float] = {
    "position_lat": SEMICIRCLES_TO_DEGREES,
    "position_long": SEMICIRCLES_TO_DEGREES,
    "distance": M_TO_KM,
    "ball_speed": MPS_TO_KMH,
    "enhanced_speed": MPS_TO_KMH,
    "speed": MPS_TO_KMH,
    "speed_1s": MPS_TO_KMH,
}

LAP_UNITS: dict[str, float] = {
    "end_position_lat": SEMICIRCLES_TO_DEGREES,
    "end_position_long": SEMICIRCLES_TO_DEGREES,
    "start_position_lat": SEMICIRCLES_TO_DEGREES,
    "start_position_long": SEMICIRCLES_TO_DEGREES,
    "avg_stroke_distance": M_TO_KM,
    "total_distance": M_TO_KM,
    "avg_speed": MPS_TO_KMH,
    "enhanced_avg_speed": MPS_TO_KMH,
    "enhanced_max_speed": MPS_TO_KMH,
    "max_speed": MPS_TO_KMH,
}

SESSION_UNITS: dict[str, float] = {
    "end_position_lat": SEMICIRCLES_TO_DEGREES,
    "end_position_long": SEMICIRCLES_TO_DEGREES,
    "nec_lat": SEMICIRCLES_TO_DEGREES,
    "nec_long": SEMICIRCLES_TO_DEGREES,
    "start_position_lat": SEMICIRCLES_TO_DEGREES,
    "start_position_long": SEMICIRCLES_TO_DEGREES,
    "swc_lat": SEMICIRCLES_TO_DEGREES,
    "swc_long": SEMICIRCLES_TO_DEGREES,
    "avg_stroke_distance": M_TO_KM,
    "total_distance": M_TO_KM,
    "avg_ball_speed": MPS_TO_KMH,
    "avg_speed": MPS_TO_KMH,
    "enhanced_avg_speed": MPS_TO_KMH,
    "enhanced_max_speed": MPS_TO_KMH,
    "max_ball_speed": MPS_TO_KMH,
    "max_speed": MPS_TO_KMH,
}


def convert_units(df: pd.DataFrame, table: Mapping[str, float]) -> pd.DataFrame:
    """Scales each of ``df``'s columns named in ``table`` by its factor.

    Columns absent from ``table`` are left untouched, as are columns whose values don't
    all coerce to numeric.
    """
    df = df.copy()

    for column, factor in table.items():
        if column not in df.columns:
            continue

        values = df[column]
        if not pd.api.types.is_numeric_dtype(values):
            values = coerce_numeric_all_or_nothing(values)
        if pd.api.types.is_numeric_dtype(values):
            df[column] = values * factor

    return df


def convert_units_mapping(row: Mapping[str, Any], table: Mapping[str, float]) -> dict[str, Any]:
    """Scales each of ``row``'s values named in ``table`` by its factor.

    The mapping counterpart of ``convert_units``, for messages consumed as plain dicts
    rather than as DataFrames. Non-numeric and missing values are left as they are.
    """
    converted = dict(row)

    for field, factor in table.items():
        value = converted.get(field)
        if isinstance(value, (int, float)):
            converted[field] = value * factor

    return converted
