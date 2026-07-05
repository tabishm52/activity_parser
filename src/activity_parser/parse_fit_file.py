"""Functions for parsing FIT files into Pandas DataFrames."""

from __future__ import annotations

import gzip
from collections.abc import Iterator
from os import PathLike
from pathlib import Path
from typing import IO, TYPE_CHECKING, Any

import fitdecode
import pandas as pd

if TYPE_CHECKING:
    from _typeshed import SupportsRead


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

    laps = pd.DataFrame(laps_rows)

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

    Message types and fields fitdecode can't resolve against the FIT SDK profile are
    kept under fitdecode's ``unknown_<num>`` names. Assumes that the FIT file is all one
    activity, i.e. chained FIT files will be merged into one set of return values.

    Args:
        file: File-like or path-like object. A path-like argument ending in ``.gz`` will
            be unzipped before processing.
        check_crc: If True, raise on a CRC mismatch instead of skipping verification.

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
