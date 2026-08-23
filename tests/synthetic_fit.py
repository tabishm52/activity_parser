"""Synthetic FIT byte builders for testing.

Each function encodes a tiny FIT message stream via the garmin-fit-sdk Encoder.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any

from garmin_fit_sdk import Encoder

FILE_ID_MESG_NUM = 0
SESSION_MESG_NUM = 18
LAP_MESG_NUM = 19
RECORD_MESG_NUM = 20
HR_MESG_NUM = 132

T0 = datetime(2026, 1, 5, 8, 0, 0, tzinfo=UTC)


def at(seconds: int) -> datetime:
    """Returns the timestamp `seconds` after the fixtures' shared start time."""
    return T0 + timedelta(seconds=seconds)


def encode(messages: list[dict[str, Any]]) -> bytes:
    """Encodes a list of FIT messages into file bytes."""
    encoder = Encoder()
    for message in messages:
        encoder.write_mesg(message)
    return encoder.close()


def dup_timestamps() -> bytes:
    """Two records sharing the same timestamp."""
    return encode(
        [
            {"mesg_num": RECORD_MESG_NUM, "timestamp": at(0), "heart_rate": 100},
            {"mesg_num": RECORD_MESG_NUM, "timestamp": at(0), "heart_rate": 999},
            {"mesg_num": RECORD_MESG_NUM, "timestamp": at(1), "heart_rate": 101},
        ]
    )


def missing_timestamp() -> bytes:
    """A record with no timestamp field at all."""
    return encode(
        [
            {"mesg_num": RECORD_MESG_NUM, "timestamp": at(0), "heart_rate": 100},
            {"mesg_num": RECORD_MESG_NUM, "heart_rate": 999},
            {"mesg_num": RECORD_MESG_NUM, "timestamp": at(1), "heart_rate": 101},
        ]
    )


def laps_only() -> bytes:
    """A manually-logged workout: lap/session/file_id summary data, zero records."""
    return encode(
        [
            {
                "mesg_num": FILE_ID_MESG_NUM,
                "type": "activity",
                "manufacturer": "garmin",
                "product": 1000,
                "time_created": T0,
            },
            {
                "mesg_num": SESSION_MESG_NUM,
                "timestamp": at(300),
                "start_time": T0,
                "sport": "running",
                "total_elapsed_time": 300.0,
            },
            {
                "mesg_num": LAP_MESG_NUM,
                "timestamp": at(150),
                "start_time": T0,
                "total_elapsed_time": 150.0,
                "total_distance": 1000.0,
            },
            {
                "mesg_num": LAP_MESG_NUM,
                "timestamp": at(300),
                "start_time": at(150),
                "total_elapsed_time": 150.0,
                "total_distance": 1500.0,
            },
        ]
    )


def multi_session() -> bytes:
    """Two file_id messages and two session messages."""
    return encode(
        [
            {
                "mesg_num": FILE_ID_MESG_NUM,
                "type": "activity",
                "manufacturer": "garmin",
                "product": 1111,
                "time_created": T0,
            },
            {
                "mesg_num": SESSION_MESG_NUM,
                "timestamp": at(60),
                "start_time": T0,
                "sport": "running",
                "total_elapsed_time": 60.0,
            },
            {
                "mesg_num": FILE_ID_MESG_NUM,
                "type": "activity",
                "manufacturer": "garmin",
                "product": 2222,
                "time_created": T0,
            },
            {
                "mesg_num": SESSION_MESG_NUM,
                "timestamp": at(120),
                "start_time": at(60),
                "sport": "cycling",
                "total_elapsed_time": 60.0,
            },
        ]
    )


def left_right_balance() -> bytes:
    """Records and a lap carrying left_right_balance, both flag states."""
    return encode(
        [
            {
                "mesg_num": RECORD_MESG_NUM,
                "timestamp": at(0),
                "heart_rate": 100,
                "power": 200,
                "left_right_balance": 180,  # right flag set, 52% -> right=52, left=48
            },
            {
                "mesg_num": RECORD_MESG_NUM,
                "timestamp": at(1),
                "heart_rate": 101,
                "power": 210,
                "left_right_balance": 52,  # no flag -> left=52, right=48
            },
            {
                "mesg_num": LAP_MESG_NUM,
                "timestamp": at(1),
                "start_time": T0,
                "total_elapsed_time": 1.0,
                "left_right_balance": 37968,  # 0x8000 | 5200 -> right=52, left=48
            },
        ]
    )


def left_right_balance_enum_quirk() -> bytes:
    """Records whose left_right_balance byte matches the FIT profile's enum keys."""
    return encode(
        [
            {
                "mesg_num": RECORD_MESG_NUM,
                "timestamp": at(0),
                "left_right_balance": 128,  # decodes to "right"
            },
            {
                "mesg_num": RECORD_MESG_NUM,
                "timestamp": at(1),
                "left_right_balance": 127,  # decodes to "mask"
            },
            {
                "mesg_num": RECORD_MESG_NUM,
                "timestamp": at(2),
                "left_right_balance": 180,  # decodes to a plain int, unaffected
            },
        ]
    )


def coercion_skip() -> bytes:
    """A record field that decodes to a tuple in one row, a scalar in others."""
    return encode(
        [
            {
                "mesg_num": RECORD_MESG_NUM,
                "timestamp": at(0),
                "heart_rate": 100,
                "temperature": 20,
                "left_power_phase": 10,
            },
            {
                "mesg_num": RECORD_MESG_NUM,
                "timestamp": at(1),
                "heart_rate": 101,
                "left_power_phase": [10, 20],
            },
            {
                "mesg_num": RECORD_MESG_NUM,
                "timestamp": at(2),
                "heart_rate": 102,
                "temperature": 21,
                "left_power_phase": 30,
            },
        ]
    )


def heart_rate_merge() -> bytes:
    """An hr stream reports 150 bpm for the first two records, none for the third."""
    return encode(
        [
            {"mesg_num": RECORD_MESG_NUM, "timestamp": at(0), "heart_rate": 100},
            {"mesg_num": RECORD_MESG_NUM, "timestamp": at(1), "heart_rate": 100},
            {"mesg_num": RECORD_MESG_NUM, "timestamp": at(2), "heart_rate": 100},
            {
                "mesg_num": HR_MESG_NUM,
                "timestamp": at(0),
                "fractional_timestamp": 0.0,  # required on the anchor or merge no-ops
                "event_timestamp": 0.0,
                "filtered_bpm": 150,
            },
            {
                "mesg_num": HR_MESG_NUM,
                "event_timestamp": [0.25, 0.5, 0.75, 1.0, 1.25, 1.5, 1.75, 2.0],
                "filtered_bpm": [150, 150, 150, 150, 150, 150, 150, 150],
            },
        ]
    )
