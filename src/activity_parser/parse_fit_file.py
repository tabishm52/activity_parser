"""Functions for parsing FIT files into Pandas DataFrames."""

from __future__ import annotations

import contextlib
import gzip
import zlib
from collections.abc import Generator, Mapping
from os import PathLike
from pathlib import Path
from typing import IO, TYPE_CHECKING, Any, cast

import pandas as pd
from garmin_fit_sdk import Decoder, Stream

from .exceptions import FitError
from .fit_fields import LAP_UNITS, RECORD_UNITS, SESSION_UNITS, convert_units, convert_units_mapping
from .output import Activity
from .postprocess import coerce_numeric_columns, index_by_time

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

# left_right_balance is bit-packed: one bit flags the right side, the rest is that
# side's percentage. Per-record is uint8 (percentage); lap/session/segment_lap
# aggregates use a higher-precision uint16 (percentage x100).
LEFT_RIGHT_BALANCE_COLUMN = "left_right_balance"
LEFT_RIGHT_BALANCE_RIGHT_FLAG = 0x80
LEFT_RIGHT_BALANCE_PERCENT_MASK = 0x7F
LEFT_RIGHT_BALANCE_RIGHT_FLAG_100 = 0x8000
LEFT_RIGHT_BALANCE_PERCENT_MASK_100 = 0x3FFF


def coalesce_enhanced_columns(df: pd.DataFrame, pairs: Mapping[str, str]) -> pd.DataFrame:
    """Prefers each enhanced FIT column's values over its base counterpart."""
    df = df.copy()
    for base, enhanced in pairs.items():
        if enhanced not in df.columns:
            continue
        df[base] = df[enhanced].combine_first(df[base]) if base in df.columns else df[enhanced]
    return df


def add_fractional_columns(df: pd.DataFrame, pairs: Mapping[str, str]) -> pd.DataFrame:
    """Adds each fractional-precision FIT column into its base counterpart."""
    df = df.copy()
    for base, fractional in pairs.items():
        if fractional not in df.columns:
            continue
        df[base] = df[base] + df[fractional].fillna(0) if base in df.columns else df[fractional]
    return df


def split_left_right_balance(
    df: pd.DataFrame,
    right_flag: int,
    percent_mask: int,
    percent_scale: float,
) -> pd.DataFrame:
    """Adds left_balance/right_balance decoded from left_right_balance."""
    if LEFT_RIGHT_BALANCE_COLUMN not in df.columns:
        return df

    # A quirk in the FIT profile renders right_flag/percent_mask as "right"/"mask"
    # strings instead of ints; map them back before casting.
    raw = df[LEFT_RIGHT_BALANCE_COLUMN].replace({"right": right_flag, "mask": percent_mask})
    present = raw.dropna().astype(int)
    is_right = (present & right_flag) != 0
    percent = (present & percent_mask).astype(float) / percent_scale
    right = percent.where(is_right, 100 - percent)

    df = df.copy()
    df["left_balance"] = (100 - right).reindex(df.index)
    df["right_balance"] = right.reindex(df.index)
    return df


def _flatten_developer_fields(row: dict[str, Any], field_names: dict[int, str]) -> dict[str, Any]:
    """Splices developer_fields' {ordinal: value} entries back in by name."""
    developer_fields = row.pop("developer_fields", None)
    if not developer_fields:
        return row

    for ordinal, value in developer_fields.items():
        name = field_names.get(ordinal, f"developer_field_{ordinal}")
        row[name] = tuple(value) if isinstance(value, list) else value

    return row


def _normalize_row(row: dict[str, Any], field_names: dict[int, str]) -> dict[str, Any]:
    """Renames int field keys to unknown_<n>, tuple-izes arrays, flattens dev fields."""
    row = _flatten_developer_fields(dict(row), field_names)

    normalized: dict[str, Any] = {}
    for key, value in row.items():
        name = f"unknown_{key}" if isinstance(key, int) else key
        normalized[name] = tuple(value) if isinstance(value, list) else value

    return normalized


def _normalize_messages(
    messages: Mapping[str, list[dict[str, Any]]],
) -> dict[str, list[dict[str, Any]]]:
    """Normalizes decoded FIT messages.

    These are per-element operations that don't benefit from vectorization, so they are
    done as plain dict manipulation before DataFrame construction.

    1. Strips the ``_mesgs`` suffix from message-type keys.
    2. Renames an all-digit message-type key, or an ``int`` field key, to ``unknown_<n>``.
    3. Flattens ``developer_fields`` by name via ``field_description_mesgs``.
    4. Converts ``list`` field values to ``tuple``.
    """
    field_names = {
        desc["key"]: desc["field_name"] for desc in messages.get("field_description_mesgs", [])
    }

    result: dict[str, list[dict[str, Any]]] = {}
    for key, rows in messages.items():
        name = key[:-6] if key.endswith("_mesgs") else key
        if name.isdigit():
            name = f"unknown_{name}"

        if name == "field_description":
            # "key" is FIT decoder bookkeeping, not a real FIT field.
            result[name] = [{k: v for k, v in row.items() if k != "key"} for row in rows]
        else:
            result[name] = [_normalize_row(row, field_names) for row in rows]

    return result


def decode_fit(fit_file: SupportsRead[bytes], check_crc: bool) -> dict[str, list[dict[str, Any]]]:
    """Decodes a FIT file-like object into rows grouped by message type."""
    try:
        data = bytearray(fit_file.read())
    # gzip.open (open_fit_file) is lazy; decompression errors surface here.
    except (gzip.BadGzipFile, zlib.error, EOFError) as e:
        raise FitError(str(e)) from e

    messages, errors = Decoder(Stream.from_byte_array(data)).read(
        enable_crc_check=check_crc, merge_heart_rates=False
    )
    if errors:
        raise FitError(str(errors[0])) from errors[0]

    return _normalize_messages(cast(Mapping[str, list[dict[str, Any]]], messages))


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


@contextlib.contextmanager
def open_fit_file(
    file: str | PathLike[str] | IO[bytes],
) -> Generator[SupportsRead[bytes], None, None]:
    """Opens a FIT path (auto-unzipping ``.gz``) or passes through a file-like object."""
    if isinstance(file, (str, PathLike)):
        ext = Path(file).suffix
        opener = gzip.open if ext.lower() == ".gz" else open
        with opener(file, "rb") as fit_file:
            yield fit_file
    else:
        yield file


def parse_fit(
    file: str | PathLike[str] | IO[bytes],
    check_crc: bool = False,
) -> tuple[pd.DataFrame, pd.DataFrame, Activity]:
    """Loads a FIT activity into Pandas DataFrames.

    Known fields are converted to typed, canonically-named columns. Unknown fields are
    kept under an ``unknown_<n>`` name. The ``session`` and ``file_id`` messages are
    summarized into the returned ``Activity``; all other message types are discarded.

    Assumes that the FIT file is all one activity, i.e. chained FIT files will be
    merged into one set of return values. If a file has more than one ``session`` or
    ``file_id`` message, only the first of each is used.

    Args:
        file: Binary file-like or path-like object. A path-like argument ending in
            ``.gz`` will be unzipped before processing.
        check_crc: If True, verifies CRC integrity of the FIT file. If False, CRC
            verification is skipped.

    Returns:
        Tuple containing records, laps, and an ``Activity`` summary.

    Raises:
        FitError: The FIT file fails to decode (e.g. invalid header, or a CRC mismatch
            when ``check_crc`` is True).
    """
    with open_fit_file(file) as fit_file:
        messages = decode_fit(fit_file, check_crc=check_crc)

    session = messages.get("session", [None])[0]
    file_id = messages.get("file_id", [None])[0]

    records = pd.DataFrame(messages.get("record", []))
    records = coerce_numeric_columns(records)
    records = index_by_time(records, "timestamp")
    records = convert_units(records, RECORD_UNITS)
    records = coalesce_enhanced_columns(records, FIT_RECORDS_ENHANCED_PAIRS)
    records = add_fractional_columns(records, FIT_RECORDS_FRACTIONAL_PAIRS)
    records = split_left_right_balance(
        records,
        right_flag=LEFT_RIGHT_BALANCE_RIGHT_FLAG,
        percent_mask=LEFT_RIGHT_BALANCE_PERCENT_MASK,
        percent_scale=1.0,
    )
    records = records.rename(columns=FIT_RECORD_RENAME)

    laps = pd.DataFrame(messages.get("lap", []))
    laps = coerce_numeric_columns(laps)
    laps = convert_units(laps, LAP_UNITS)
    laps = coalesce_enhanced_columns(laps, FIT_LAPS_ENHANCED_PAIRS)
    laps = add_fractional_columns(laps, FIT_LAPS_FRACTIONAL_PAIRS)
    laps = split_left_right_balance(
        laps,
        right_flag=LEFT_RIGHT_BALANCE_RIGHT_FLAG_100,
        percent_mask=LEFT_RIGHT_BALANCE_PERCENT_MASK_100,
        percent_scale=100.0,
    )

    activity = build_activity(convert_units_mapping(session or {}, SESSION_UNITS), file_id)

    return records, laps, activity


def parse_fit_raw(
    file: str | PathLike[str] | IO[bytes],
    check_crc: bool = False,
) -> dict[str, pd.DataFrame]:
    """Loads every message type in a FIT file into its own raw Pandas DataFrame.

    Returns one DataFrame per FIT message type present in the file (e.g. ``record``,
    ``lap``, ``session``, ``device_info``, ...) with only structural normalization
    applied: field values are decoded as-is, in FIT-native units (e.g. positions in
    semicircles, distances in meters, speeds in m/s) rather than this package's usual
    degrees/km/kph. Developer fields are flattened into named columns and array fields
    become tuples, but there's no renaming, unit conversion, or other post-processing.

    Message and field names that can't be resolved against the FIT profile are keyed
    under ``unknown_<n>`` names. Chained FIT files have same-named messages merged
    across the chain.

    Args:
        file: Binary file-like or path-like object. A path-like argument ending in
            ``.gz`` will be unzipped before processing.
        check_crc: If True, verifies CRC integrity of the FIT file. If False, CRC
            verification is skipped.

    Returns:
        Dict mapping FIT message type name to its raw DataFrame. A message type absent
        from the file is absent from the dict.

    Raises:
        FitError: The FIT file fails to decode (e.g. invalid header, or a CRC mismatch
            when ``check_crc`` is True).
    """
    with open_fit_file(file) as fit_file:
        messages = decode_fit(fit_file, check_crc=check_crc)

    return {name: pd.DataFrame(rows) for name, rows in messages.items()}
