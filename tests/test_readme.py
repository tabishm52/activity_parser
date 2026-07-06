"""Keeps README.md's column tables in sync with default_columns."""

import re
from pathlib import Path

from activity_parser.default_columns import DEFAULT_LAP_COLUMNS, DEFAULT_RECORD_COLUMNS

README = Path(__file__).parent.parent / "README.md"
COLUMN_NAME = re.compile(r"`(\w+)`")


def _section(text: str, start_heading: str, end_heading: str) -> str:
    start = text.index(start_heading)
    end = text.index(end_heading, start)
    return text[start:end]


def _table_column_names(section: str) -> set[str]:
    names: set[str] = set()
    for line in section.splitlines():
        if not line.startswith("|"):
            continue
        first_cell = line.split("|")[1]
        names.update(COLUMN_NAME.findall(first_cell))
    return names


def test_readme_records_table_matches_default_columns():
    text = README.read_text()
    section = _section(text, "### Records", "### Laps")
    assert _table_column_names(section) == set(DEFAULT_RECORD_COLUMNS)


def test_readme_laps_table_matches_default_columns():
    text = README.read_text()
    section = _section(text, "### Laps", "### Extra")
    assert _table_column_names(section) == set(DEFAULT_LAP_COLUMNS)
