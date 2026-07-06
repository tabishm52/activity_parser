"""Functions for parsing FIT files into Pandas DataFrames."""

from __future__ import annotations

import gzip
from collections.abc import Iterator, Mapping
from os import PathLike
from pathlib import Path
from typing import IO, TYPE_CHECKING, Any

import fitdecode
import pandas as pd

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


def coalesce_enhanced_columns(df: pd.DataFrame, pairs: Mapping[str, str]) -> pd.DataFrame:
    """Prefers each enhanced FIT column's values over its base counterpart."""
    df = df.copy()
    for base, enhanced in pairs.items():
        if enhanced not in df.columns:
            continue
        df[base] = df[enhanced].combine_first(df[base]) if base in df.columns else df[enhanced]
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


def parse_fit_frames(
    fit_file: SupportsRead[bytes],
    check_crc: bool = False,
) -> tuple[pd.DataFrame, pd.DataFrame, dict[str, Any]]:
    """Parse FIT frames from an open file object."""
    records_rows: list[dict[str, Any]] = []
    laps_rows: list[dict[str, Any]] = []
    extra_rows: dict[str, list[dict[str, Any]]] = {}

    for frame in copy_fit_frames(fit_file, check_crc=check_crc):
        row = frame_to_dict(frame)
        if frame.name == "record":
            records_rows.append(row)
        elif frame.name == "lap":
            laps_rows.append(row)
        else:
            extra_rows.setdefault(frame.name, []).append(row)

    records = pd.DataFrame(records_rows)

    # None-valued fields cause object dtype; coerce numeric columns to float64.
    for col in records.select_dtypes(include="object").columns:
        coerced = pd.to_numeric(records[col], errors="coerce")
        if coerced.notna().sum() == records[col].notna().sum():
            records[col] = coerced

    # FIT files occasionally have duplicate timestamps.
    if "timestamp" in records.columns:
        records = records.set_index("timestamp")
    else:
        records.index = pd.Index(records.index, name="timestamp")

    records = records[records.index.notna()]
    records = records[~records.index.duplicated()]

    records = coalesce_enhanced_columns(records, FIT_RECORDS_ENHANCED_PAIRS)
    records = records.rename(columns=FIT_RECORD_RENAME)

    laps = pd.DataFrame(laps_rows)
    laps = coalesce_enhanced_columns(laps, FIT_LAPS_ENHANCED_PAIRS)

    extra: dict[str, Any] = {}
    for name, rows in extra_rows.items():
        if len(rows) == 1:
            extra[name] = rows[0]
        else:
            extra[name] = pd.DataFrame(rows)

    return records, laps, extra


def parse_fit(
    file: str | PathLike[str] | IO[bytes],
    check_crc: bool = False,
) -> tuple[pd.DataFrame, pd.DataFrame, dict[str, Any]]:
    """Loads a FIT activity into Pandas DataFrames.

    Known message types and fields are converted to typed, canonically-named columns.
    Unknown message types and fields are returned under fitdecode's ``unknown_<num>``
    names.

    Assumes that the FIT file is all one activity, i.e. chained FIT files will be
    merged into one set of return values.

    Args:
        file: File-like or path-like object. A path-like argument ending in ``.gz`` will
            be unzipped before processing.
        check_crc: If True, raises ``fitdecode.FitCRCError`` on a CRC mismatch in the
            FIT file. If False, CRC verification is skipped.

    Returns:
        Tuple containing records, laps, and additional metadata.
    """
    is_path = isinstance(file, (str, PathLike))

    if is_path:
        ext = Path(file).suffix
        opener = gzip.open if ext.lower() == ".gz" else open
        with opener(file, "rb") as fit_file:
            records, laps, extra = parse_fit_frames(fit_file, check_crc=check_crc)
    else:
        records, laps, extra = parse_fit_frames(file, check_crc=check_crc)

    return records, laps, extra
