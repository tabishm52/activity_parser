"""Regenerates the gen-*.fit fixtures using the official garmin-fit-sdk Encoder.

Each fixture targets one guard in parse_fit_file.parse_fit_frames that the vendored
real-device fixtures never exercise. Run with:

    uv run python tests/files/fit/generate_fixtures.py

Output is deterministic, so a re-run should produce byte-identical files.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

from garmin_fit_sdk import Encoder

FILES = Path(__file__).parent

FILE_ID_MESG_NUM = 0
SESSION_MESG_NUM = 18
LAP_MESG_NUM = 19
RECORD_MESG_NUM = 20

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


def write(name: str, messages: list[dict[str, Any]]) -> None:
    """Encodes `messages` and writes them to `name` in this directory."""
    (FILES / name).write_bytes(encode(messages))


def generate_dup_timestamps() -> None:
    """Two records sharing the same timestamp."""
    write(
        "gen-dup-timestamps.fit",
        [
            {"mesg_num": RECORD_MESG_NUM, "timestamp": at(0), "heart_rate": 100},
            {"mesg_num": RECORD_MESG_NUM, "timestamp": at(0), "heart_rate": 999},
            {"mesg_num": RECORD_MESG_NUM, "timestamp": at(1), "heart_rate": 101},
        ],
    )


def generate_missing_timestamp() -> None:
    """A record with no timestamp field at all."""
    write(
        "gen-missing-timestamp.fit",
        [
            {"mesg_num": RECORD_MESG_NUM, "timestamp": at(0), "heart_rate": 100},
            {"mesg_num": RECORD_MESG_NUM, "heart_rate": 999},
            {"mesg_num": RECORD_MESG_NUM, "timestamp": at(1), "heart_rate": 101},
        ],
    )


def generate_laps_only() -> None:
    """A manually-logged workout: lap/session/file_id summary data, zero records."""
    write(
        "gen-laps-only.fit",
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
        ],
    )


def generate_multi_session() -> None:
    """Two file_id messages and two session messages."""
    write(
        "gen-multi-session.fit",
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
        ],
    )


def generate_left_right_balance() -> None:
    """Records and a lap carrying left_right_balance, both flag states.

    left_right_balance is a bit-packed byte: 0x80 flags the right side, and
    the low 7 bits are that side's percentage contribution.
    """
    write(
        "gen-left-right-balance.fit",
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
                "left_right_balance": 180,
            },
        ],
    )


def generate_coercion_skip() -> None:
    """A record field that decodes to a tuple in one row, a scalar in others.

    left_power_phase is an array field; a row with two values decodes to a
    tuple rather than a scalar. temperature is included alongside it with a
    genuinely missing value in one row.
    """
    write(
        "gen-coercion-skip.fit",
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
        ],
    )


def main() -> None:
    """Regenerates every gen-*.fit fixture."""
    generate_dup_timestamps()
    generate_missing_timestamp()
    generate_laps_only()
    generate_multi_session()
    generate_left_right_balance()
    generate_coercion_skip()


if __name__ == "__main__":
    main()
