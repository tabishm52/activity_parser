"""Health check and column coverage report for an archive of activity files, by type.

Usage: python check_archive.py path/to/archive [--all-columns]
"""

import argparse
import functools
from dataclasses import dataclass, fields
from pathlib import Path

import pandas as pd
from _parse_directory import activity_file_type, parse_directory

from activity_parser import ActivityParser, ParseError


@dataclass(frozen=True)
class ActivityCheck:
    path: Path
    file_type: str
    strict_ok: bool
    error: str | None
    n_records: int
    record_columns: tuple[str, ...]


def check_activity(
    path: Path,
    strict_parser: ActivityParser | None = None,
    lenient_parser: ActivityParser | None = None,
) -> ActivityCheck:
    """Processes one activity file to check for parsing errors.

    Tries strict parsing first (CRC-verified FIT, well-formed XML), falling back to
    lenient parsing. Never raises ``ParseError``, even when lenient parsing fails.
    Picklable and suitable for use inside multiprocessing pools.

    Args:
        path: File to parse.
        strict_parser: Parser to try first. Defaults to CRC-verified, strict-XML,
            default-curated-columns settings.
        lenient_parser: Fallback parser. Defaults to ``ActivityParser()``.

    Returns:
        An ActivityCheck summary of parsing errors and (if available) record fields.
    """
    strict_parser = strict_parser or ActivityParser(check_crc=True, strict_xml=True)
    lenient_parser = lenient_parser or ActivityParser()

    file_type = activity_file_type(path)
    assert file_type is not None  # parse_directory only calls this on matched paths

    try:
        records, _, _ = strict_parser.parse(path)
        return ActivityCheck(path, file_type, True, None, len(records), tuple(records.columns))
    except ParseError:
        pass

    try:
        records, _, _ = lenient_parser.parse(path)
        return ActivityCheck(path, file_type, False, None, len(records), tuple(records.columns))
    except ParseError as error:
        return ActivityCheck(path, file_type, False, str(error), 0, ())


def print_type_report(file_type: str, files: pd.DataFrame) -> None:
    """Prints one activity type's section: pass/fail counts, failures, column coverage."""
    checked, ok = len(files), files["parse_ok"].sum()
    lenient = (files["parse_ok"] & ~files["strict_ok"]).sum()

    print(f"\n=== {file_type} ({checked} files) ===")
    print(f"{ok} ok, {checked - ok} failed, {lenient} needed lenient parsing.")

    failed = files.loc[~files["parse_ok"]].sort_values("path")
    if not failed.empty:
        print("\nFailures:")
        for row in failed.itertuples():
            print(f"  {row.path}: {row.error}")

    if ok:
        records = files.loc[files["parse_ok"], "n_records"]
        print(
            f"\nRecords per file: min {records.min()}, median {records.median():.0f}, "
            f"max {records.max()}."
        )

        columns = files.loc[files["parse_ok"], "record_columns"].explode().value_counts()
        print("\nRecord column coverage:")
        for column, count in columns.items():
            print(f"  {column:<20} {count:>5} files ({count / ok:.0%})")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("directory", type=Path)
    parser.add_argument(
        "--all-columns",
        action="store_true",
        help="Report every column present in each file, not just the standard curated set.",
    )
    args = parser.parse_args()

    strict_parser = ActivityParser(
        include_all_columns=args.all_columns, check_crc=True, strict_xml=True
    )
    lenient_parser = ActivityParser(include_all_columns=args.all_columns)
    task = functools.partial(
        check_activity, strict_parser=strict_parser, lenient_parser=lenient_parser
    )

    checks = [check for _, check in parse_directory(args.directory, task)]

    files = pd.DataFrame(checks, columns=[f.name for f in fields(ActivityCheck)])
    files["parse_ok"] = files["error"].isna()

    checked, ok = len(files), files["parse_ok"].sum()
    print(f"Checked {checked} files: {ok} ok, {checked - ok} failed.")

    for file_type, group in files.groupby("file_type"):
        print_type_report(str(file_type), group)


if __name__ == "__main__":
    main()
