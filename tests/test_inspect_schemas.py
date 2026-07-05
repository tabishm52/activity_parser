"""Tests for scripts/inspect_schemas.py against the fixture files."""

import sys
from pathlib import Path

import pytest

FILES = Path(__file__).parent / "files"
SCRIPTS_DIR = Path(__file__).parent.parent / "scripts"

sys.path.insert(0, str(SCRIPTS_DIR))
import inspect_schemas  # noqa: E402


@pytest.mark.parametrize(
    ("filename", "root_label"),
    [
        ("sample.tcx", "TCX"),
        ("sample.gpx", "GPX 1.1"),
        ("gpx10.gpx", "GPX 1.0"),
    ],
)
def test_root_label(filename, root_label):
    report = inspect_schemas.inspect_file(FILES / filename)
    assert report.root_label == root_label


def test_detects_known_extensions():
    report = inspect_schemas.inspect_file(FILES / "sample.gpx")
    assert "TrackPointExtension/v2" in report.extensions_seen
    assert "bare <power>" in report.extensions_seen
    assert not report.unknown_counts


def test_flags_unknown_extension():
    report = inspect_schemas.inspect_file(FILES / "unknown_extension.gpx")
    assert report.unknown_counts["{urn:example:unknown-vendor}stress"] == 2


def test_flags_coercion_failure():
    report = inspect_schemas.inspect_file(FILES / "bad_speed.gpx")
    assert report.coercion_failures == {"speed": "n/a"}


def test_lap_inspection_does_not_flag_nested_trackpoint_fields():
    # Regression: walking a <Lap> before removing its nested <Track>/<Trackpoint>
    # elements would re-descend into trackpoint fields and flag them as unknown
    # against the lap field table.
    report = inspect_schemas.inspect_file(FILES / "sample.tcx")
    assert not report.unknown_counts


def test_find_files_recurses_directory():
    files = inspect_schemas.find_files([str(FILES)])
    names = {f.name for f in files}
    assert "sample.tcx" in names
    assert "sample.gpx" in names
    assert all(inspect_schemas._is_activity_xml(f) for f in files)


def test_main_reports_summary_for_directory(capsys):
    exit_code = inspect_schemas.main([str(FILES)])
    assert exit_code == 0
    out = capsys.readouterr().out
    assert "Summary across" in out
