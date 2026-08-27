"""Per-sport summary rollup for an archive of activity files.

Usage: python summarize_archive.py path/to/archive
"""

import argparse
from dataclasses import dataclass, fields
from pathlib import Path

import pandas as pd
from _parse_directory import parse_directory

from activity_parser import ActivityParser

# Built once per worker process and reused for every file it handles
PARSER = ActivityParser()


@dataclass(frozen=True)
class ActivitySummary:
    path: Path
    sport: str | None
    start_time: pd.Timestamp | None
    total_calories: float | None
    duration_s: float | None
    distance_km: float | None


def summarize_activity(path: Path) -> ActivitySummary:
    """Processing one activity file into summary metrics.

    Picklable and suitable for use inside multiprocessing pools.

    Args:
        path: File to parse.

    Returns:
        An ActivitySummary of activity attributes and metrics.
    """
    records, _, activity = PARSER.parse(path)

    # Directly compute duration and distance, instead of picking them out of Activity,
    # since TCX/GPX do not populate these Activity fields.

    duration_s = None
    if isinstance(records.index, pd.DatetimeIndex) and not records.index.empty:
        duration_s = (records.index.max() - records.index.min()).total_seconds()

    distance_km = None
    if "distance" in records.columns:
        # distance is cumulative, so its range over the file is the total distance.
        distance_km = records["distance"].max() - records["distance"].min()

    return ActivitySummary(
        path=path,
        sport=activity.sport,
        start_time=activity.start_time,
        total_calories=activity.total_calories,
        duration_s=duration_s,
        distance_km=distance_km,
    )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("directory", type=Path)
    args = parser.parse_args()

    metrics = [metric for _, metric in parse_directory(args.directory, summarize_activity)]

    df = pd.DataFrame(metrics, columns=[f.name for f in fields(ActivitySummary)])

    print(f"{len(df)} activities parsed.")
    if df.empty:
        return
    print(f"Date range: {df['start_time'].min()} to {df['start_time'].max()}")

    # dropna=False since GPX never records a sport
    by_sport = df.groupby("sport", dropna=False)
    summary = pd.DataFrame(
        {
            "activities": by_sport.size(),
            "distance_km": by_sport["distance_km"].sum(),
            "duration_h": by_sport["duration_s"].sum() / 3600,
            "total_calories": by_sport["total_calories"].sum(),
        }
    )
    print("\nPer sport:")
    print(summary.round(1).to_string())


if __name__ == "__main__":
    main()
