"""Functions for parsing FIT files into Pandas DataFrames."""

from __future__ import annotations

import gzip
from collections.abc import Iterator, Mapping
from os import PathLike
from pathlib import Path
from typing import IO, TYPE_CHECKING, Any

import fitdecode
import pandas as pd

from .output import Activity

if TYPE_CHECKING:
    from _typeshed import SupportsRead

# FIT fields that we rename in our processing
FIT_RECORD_RENAME: dict[str, str] = {
    "position_lat": "latitude",
    "position_long": "longitude",
}

# Some fields have higher-precision versions, which we prefer when available
FIT_RECORDS_ENHANCED_PAIRS: dict[str, str] = {
    "altitude": "enhanced_altitude",
    "speed": "enhanced_speed",
}
FIT_LAPS_ENHANCED_PAIRS: dict[str, str] = {
    "avg_speed": "enhanced_avg_speed",
    "max_speed": "enhanced_max_speed",
}

# Some fields have integer and fractional parts that we combine in processing
FIT_RECORDS_FRACTIONAL_PAIRS: dict[str, str] = {
    "cadence": "fractional_cadence",
}
FIT_LAPS_FRACTIONAL_PAIRS: dict[str, str] = {
    "avg_cadence": "avg_fractional_cadence",
    "max_cadence": "max_fractional_cadence",
}

# left_right_balance is a bit-packed byte: bit 0x80 flags the right side, and the
# remaining 7 bits (0x7F) are that side's percentage contribution directly (0-100)
LEFT_RIGHT_BALANCE_RIGHT_FLAG = 0x80
LEFT_RIGHT_BALANCE_PERCENT_MASK = 0x7F


def coalesce_enhanced_columns(df: pd.DataFrame, pairs: Mapping[str, str]) -> pd.DataFrame:
    """Prefers each enhanced FIT column's values over its base counterpart."""
    df = df.copy()
    for base, enhanced in pairs.items():
        if enhanced not in df.columns:
            continue
        df[base] = df[enhanced].combine_first(df[base]) if base in df.columns else df[enhanced]
    return df


def add_fractional_columns(df: pd.DataFrame, pairs: Mapping[str, str]) -> pd.DataFrame:
    """Adds each fractional-precision FIT column into its base cadence counterpart."""
    df = df.copy()
    for base, fractional in pairs.items():
        if fractional not in df.columns:
            continue
        df[base] = df[base] + df[fractional].fillna(0) if base in df.columns else df[fractional]
    return df


def split_left_right_balance(df: pd.DataFrame, column: str = "left_right_balance") -> pd.DataFrame:
    """Splits FIT's bit-packed left_right_balance byte into left_balance/right_balance."""
    if column not in df.columns:
        return df
    df = df.copy()
    raw = df.pop(column)
    present = raw.dropna().astype(int)
    is_right = (present & LEFT_RIGHT_BALANCE_RIGHT_FLAG) != 0
    percent = (present & LEFT_RIGHT_BALANCE_PERCENT_MASK).astype(float)
    right = percent.where(is_right, 100 - percent)
    df["left_balance"] = (100 - right).reindex(df.index)
    df["right_balance"] = right.reindex(df.index)
    return df


def copy_fit_frames(
    fit_file: SupportsRead[bytes],
    check_crc: bool,
) -> Iterator[fitdecode.FitDataMessage]:
    """Yields FIT data frames from a file-like object."""
    processor = fitdecode.StandardUnitsDataProcessor()
    crc_mode = fitdecode.CrcCheck.RAISE if check_crc else fitdecode.CrcCheck.DISABLED
    for frame in fitdecode.FitReader(fit_file, processor=processor, check_crc=crc_mode):
        if isinstance(frame, fitdecode.FitDataMessage):
            yield frame


def frame_to_dict(frame: fitdecode.FitDataMessage) -> dict[str, Any]:
    """Convert one FIT frame to a dict."""
    return {field.name: field.value for field in frame.fields}


def build_activity(session: dict[str, Any] | None, file_id: dict[str, Any] | None) -> Activity:
    """Builds an ``Activity`` summary from a FIT file's ``session``/``file_id`` messages."""
    session = session or {}
    file_id = file_id or {}

    start_time = session.get("start_time")
    if start_time is not None:
        start_time = pd.Timestamp(start_time)

    creator = file_id.get("product_name")
    if creator is None:
        manufacturer = file_id.get("manufacturer")
        product = file_id.get("garmin_product") or file_id.get("product")
        creator = " ".join(str(part) for part in (manufacturer, product) if part) or None

    return Activity(
        sport=session.get("sport"),
        start_time=start_time,
        total_elapsed_time=session.get("total_elapsed_time"),
        total_distance=session.get("total_distance"),
        total_calories=session.get("total_calories"),
        avg_heart_rate=session.get("avg_heart_rate"),
        max_heart_rate=session.get("max_heart_rate"),
        avg_speed=session.get("avg_speed"),
        max_speed=session.get("max_speed"),
        creator=creator,
    )


def parse_fit_frames(
    fit_file: SupportsRead[bytes],
    check_crc: bool = False,
) -> tuple[pd.DataFrame, pd.DataFrame, Activity]:
    """Parse FIT frames from an open file object."""
    records_rows: list[dict[str, Any]] = []
    laps_rows: list[dict[str, Any]] = []
    session: dict[str, Any] | None = None
    file_id: dict[str, Any] | None = None

    for frame in copy_fit_frames(fit_file, check_crc=check_crc):
        row = frame_to_dict(frame)
        if frame.name == "record":
            records_rows.append(row)
        elif frame.name == "lap":
            laps_rows.append(row)
        elif frame.name == "session" and session is None:
            session = row
        elif frame.name == "file_id" and file_id is None:
            file_id = row

    records = pd.DataFrame(records_rows)

    # None-valued fields cause object dtype; coerce numeric columns to float64.
    for col in records.select_dtypes(include="object").columns:
        coerced = pd.to_numeric(records[col], errors="coerce")
        if coerced.notna().sum() == records[col].notna().sum():
            records[col] = coerced

    # FIT files occasionally have duplicate timestamps.
    if "timestamp" in records.columns:
        records = records.set_index("timestamp")
    elif records.empty:
        records.index = pd.DatetimeIndex([], name="timestamp")
    else:
        records.index = pd.Index(records.index, name="timestamp")

    records = records[records.index.notna()]
    records = records[~records.index.duplicated()]

    records = coalesce_enhanced_columns(records, FIT_RECORDS_ENHANCED_PAIRS)
    records = add_fractional_columns(records, FIT_RECORDS_FRACTIONAL_PAIRS)
    records = split_left_right_balance(records)
    records = records.rename(columns=FIT_RECORD_RENAME)

    laps = pd.DataFrame(laps_rows)
    laps = coalesce_enhanced_columns(laps, FIT_LAPS_ENHANCED_PAIRS)
    laps = add_fractional_columns(laps, FIT_LAPS_FRACTIONAL_PAIRS)
    laps = split_left_right_balance(laps)

    activity = build_activity(session, file_id)

    return records, laps, activity


def parse_fit(
    file: str | PathLike[str] | IO[bytes],
    check_crc: bool = False,
) -> tuple[pd.DataFrame, pd.DataFrame, Activity]:
    """Loads a FIT activity into Pandas DataFrames.

    Known message types and fields are converted to typed, canonically-named columns.
    Unknown message types and fields are returned under fitdecode's ``unknown_<num>``
    names. The ``session`` and ``file_id`` messages are summarized into the returned
    ``Activity``; all other message types (``device_info``, proprietary ``unknown_<n>``
    messages, etc.) are discarded.

    Assumes that the FIT file is all one activity, i.e. chained FIT files will be
    merged into one set of return values. If a file has more than one ``session`` or
    ``file_id`` message, only the first of each is used.

    Args:
        file: File-like or path-like object. A path-like argument ending in ``.gz`` will
            be unzipped before processing.
        check_crc: If True, raises ``fitdecode.FitCRCError`` on a CRC mismatch in the
            FIT file. If False, CRC verification is skipped.

    Returns:
        Tuple containing records, laps, and an ``Activity`` summary.
    """
    is_path = isinstance(file, (str, PathLike))

    if is_path:
        ext = Path(file).suffix
        opener = gzip.open if ext.lower() == ".gz" else open
        with opener(file, "rb") as fit_file:
            records, laps, activity = parse_fit_frames(fit_file, check_crc=check_crc)
    else:
        records, laps, activity = parse_fit_frames(file, check_crc=check_crc)

    return records, laps, activity
