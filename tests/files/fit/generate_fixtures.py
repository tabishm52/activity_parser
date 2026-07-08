"""Regenerates the gen-*.fit fixtures using the official garmin-fit-sdk Encoder.

Each fixture targets one guard in parse_fit_file.parse_fit_frames that the two
vendored real-device fixtures never exercise (see tests/files/README.md). Run with:

    uv run python tests/files/fit/generate_fixtures.py

Output is deterministic (no wall-clock data is embedded), so a re-run should produce
byte-identical files.
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
    return T0 + timedelta(seconds=seconds)


def encode(messages: list[dict[str, Any]]) -> bytes:
    encoder = Encoder()
    for message in messages:
        encoder.write_mesg(message)
    return encoder.close()


def write(name: str, messages: list[dict[str, Any]]) -> None:
    (FILES / name).write_bytes(encode(messages))


def generate_dup_timestamps() -> None:
    # Two records share a timestamp; parse_fit_frames must keep the first occurrence
    # and drop the second.
    write(
        "gen-dup-timestamps.fit",
        [
            {"mesg_num": RECORD_MESG_NUM, "timestamp": at(0), "heart_rate": 100},
            {"mesg_num": RECORD_MESG_NUM, "timestamp": at(0), "heart_rate": 999},
            {"mesg_num": RECORD_MESG_NUM, "timestamp": at(1), "heart_rate": 101},
        ],
    )


def generate_missing_timestamp() -> None:
    # A record with no timestamp field at all must be dropped as NaT, not kept with a
    # synthesized index position.
    write(
        "gen-missing-timestamp.fit",
        [
            {"mesg_num": RECORD_MESG_NUM, "timestamp": at(0), "heart_rate": 100},
            {"mesg_num": RECORD_MESG_NUM, "heart_rate": 999},
            {"mesg_num": RECORD_MESG_NUM, "timestamp": at(1), "heart_rate": 101},
        ],
    )


def generate_laps_only() -> None:
    # A manually-logged workout: lap/session/file_id summary data but zero record
    # messages.
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
    # Two file_id/session messages: build_activity's documented contract is that only
    # the first of each is used.
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
    # left_right_balance is a bit-packed byte (0x80 flags the right side); exercise
    # both flag states, on both records and a lap summary.
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
    # left_power_phase is an array field: a row with two values decodes to a tuple,
    # making the column object-dtype and non-numeric-coercible, while a sibling
    # column with only a genuinely missing value (temperature) still coerces fine.
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
    generate_dup_timestamps()
    generate_missing_timestamp()
    generate_laps_only()
    generate_multi_session()
    generate_left_right_balance()
    generate_coercion_skip()


if __name__ == "__main__":
    main()
