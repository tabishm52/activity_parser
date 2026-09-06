"""Keeps README.md's tables in sync with output.py."""

import re
from dataclasses import fields
from pathlib import Path

from activity_parser.activity import Activity
from activity_parser.parser import DEFAULT_LAP_COLUMNS, DEFAULT_RECORD_COLUMNS

README = Path(__file__).parent.parent / "README.md"
COLUMN_NAME = re.compile(r"`(\w+)`")


def _section(text: str, start_heading: str, end_heading: str) -> str:
    start = text.index(start_heading)
    end = text.index(end_heading, start)
    return text[start:end]


def _table_column_names(section: str) -> list[str]:
    names: list[str] = []
    for line in section.splitlines():
        if not line.startswith("|"):
            continue
        first_cell = line.split("|")[1]
        names.extend(COLUMN_NAME.findall(first_cell))
    return names


def test_readme_records_table_matches_default_columns():
    text = README.read_text()
    section = _section(text, "### Records", "### Laps")
    assert _table_column_names(section) == list(DEFAULT_RECORD_COLUMNS)


def test_readme_laps_table_matches_default_columns():
    text = README.read_text()
    section = _section(text, "### Laps", "### Activity")
    assert _table_column_names(section) == list(DEFAULT_LAP_COLUMNS)


def test_readme_activity_table_matches_dataclass_fields():
    text = README.read_text()
    section = _section(text, "### Activity", "## Examples")
    assert _table_column_names(section) == [f.name for f in fields(Activity)]
