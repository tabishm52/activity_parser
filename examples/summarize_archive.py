"""Per-sport summary rollup for an archive of activity files.

Usage: python summarize_archive.py path/to/archive
"""

import argparse
from dataclasses import fields
from pathlib import Path

import pandas as pd
from _parse_directory import parse_directory

from activity_parser import Activity, ActivityParser

# Built once per worker process and reused for every file it handles
PARSER = ActivityParser()


def summarize_activity(path: Path) -> Activity:
    """Parses one activity file, picklable for use inside multiprocessing pools.

    Args:
        path: File to parse.

    Returns:
        The file's Activity summary.
    """
    _, _, activity = PARSER.parse(path)
    return activity


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("directory", type=Path)
    args = parser.parse_args()

    metrics = [metric for _, metric in parse_directory(args.directory, summarize_activity)]

    df = pd.DataFrame(metrics, columns=[f.name for f in fields(Activity)])

    print(f"{len(df)} activities parsed.")
    if df.empty:
        return
    print(f"Date range: {df['start_time'].min()} to {df['start_time'].max()}")

    # dropna=False since a missing sport value is still valid
    by_sport = df.groupby("sport", dropna=False)
    summary = pd.DataFrame(
        {
            "activities": by_sport.size(),
            # min_count=1 so an all-None group sums to NaN, not 0.0.
            "distance_km": by_sport["total_distance"].sum(min_count=1),
            "duration_h": by_sport["total_elapsed_time"].sum(min_count=1) / 3600,
            "total_ascent": by_sport["total_ascent"].sum(min_count=1),
            "avg_power": by_sport["avg_power"].mean(),
            "avg_heart_rate": by_sport["avg_heart_rate"].mean(),
            "total_calories": by_sport["total_calories"].sum(min_count=1),
        }
    )
    print("\nPer sport:")
    print(summary.round(1).to_string())


if __name__ == "__main__":
    main()
