"""Tests for the example scripts under examples/."""

from pathlib import Path

import pytest
from _parse_directory import activity_file_type, find_activity_files, parse_directory
from check_archive import check_activity
from summarize_archive import summarize_activity

from activity_parser import ActivityParser, FitError

FIT_FILES = Path(__file__).parent / "files" / "fit"
TCX_FILES = Path(__file__).parent / "files" / "tcx"
GPX_FILES = Path(__file__).parent / "files" / "gpx"


def test_find_activity_files_case_insensitive_and_gz(tmp_path):
    (tmp_path / "ride.FIT").write_bytes(b"")
    (tmp_path / "ride.tcx.gz").write_bytes(b"")
    (tmp_path / "notes.txt").write_bytes(b"")
    (tmp_path / "sub").mkdir()
    (tmp_path / "sub" / "ride.gpx").write_bytes(b"")

    found = find_activity_files(tmp_path)
    assert found == sorted(
        [tmp_path / "ride.FIT", tmp_path / "ride.tcx.gz", tmp_path / "sub" / "ride.gpx"]
    )


def test_activity_file_type_case_insensitive_and_gz():
    assert activity_file_type(Path("ride.fit")) == "FIT"
    assert activity_file_type(Path("ride.TCX.gz")) == "TCX"
    assert activity_file_type(Path("notes.txt")) is None


def _summarize_or_raise(path: Path) -> str:
    if path.stem == "bad":
        raise FitError("boom")
    return path.stem


def test_parse_directory_skips_parse_errors_by_default(tmp_path):
    good1 = tmp_path / "good1.fit"
    good2 = tmp_path / "good2.fit"
    good1.write_bytes(b"")
    good2.write_bytes(b"")
    (tmp_path / "bad.fit").write_bytes(b"")

    results = dict(parse_directory(tmp_path, _summarize_or_raise))
    assert results == {good1: "good1", good2: "good2"}


def test_parse_directory_propagates_parse_errors_when_not_suppressed(tmp_path):
    (tmp_path / "bad.fit").write_bytes(b"")

    with pytest.raises(FitError):
        list(parse_directory(tmp_path, _summarize_or_raise, suppress_errors=False))


def test_check_activity_reports_type_columns_and_counts():
    check = check_activity(FIT_FILES / "garmin-fenix-5-bike.fit")
    assert check.file_type == "FIT"
    assert check.n_records > 0
    assert "distance" in check.record_columns
    assert check.strict_ok is True
    assert check.error is None


def test_check_activity_threads_all_columns():
    path = FIT_FILES / "garmin-edge-820-bike.fit"
    curated = check_activity(path)
    everything = check_activity(
        path,
        strict_parser=ActivityParser(include_all_columns=True, check_crc=True, strict_xml=True),
        lenient_parser=ActivityParser(include_all_columns=True),
    )
    assert set(everything.record_columns) > set(curated.record_columns)


def test_check_activity_reports_error_when_lenient_also_fails(tmp_path):
    bad = tmp_path / "broken.fit"
    bad.write_bytes(b"not a fit file")

    check = check_activity(bad)
    assert check.error is not None
    assert "not a fit file" in check.error.lower()
    assert check.strict_ok is False
    assert check.n_records == 0
    assert check.record_columns == ()


def _corrupt_fit_crc(tmp_path: Path) -> Path:
    path = tmp_path / "corrupt_crc.fit"
    data = bytearray((FIT_FILES / "garmin-edge-820-bike.fit").read_bytes())
    data[-1] ^= 0xFF
    path.write_bytes(data)
    return path


def _truncate_tcx(tmp_path: Path) -> Path:
    path = tmp_path / "truncated.tcx"
    path.write_text((TCX_FILES / "sample.tcx").read_text()[:2500])
    return path


@pytest.mark.parametrize("make_bad_file", [_corrupt_fit_crc, _truncate_tcx])
def test_check_activity_falls_back_to_lenient_parsing(tmp_path, make_bad_file):
    # Bad CRC / truncated XML: strict parsing fails, lenient recovery still succeeds.
    check = check_activity(make_bad_file(tmp_path))
    assert check.strict_ok is False
    assert check.n_records >= 1


def test_summarize_activity_reads_elapsed_time_and_distance_off_activity():
    row = summarize_activity(FIT_FILES / "garmin-fenix-5-bike.fit")
    assert row.total_elapsed_time is not None and row.total_elapsed_time > 0
    assert row.total_distance is not None and row.total_distance > 0


def test_summarize_activity_raises_on_unparseable_file(tmp_path):
    bad = tmp_path / "broken.fit"
    bad.write_bytes(b"not a fit file")

    with pytest.raises(FitError, match="not a fit file"):
        summarize_activity(bad)


def test_summarize_activity_leaves_elapsed_time_none_without_timestamp_index():
    # DeveloperData.fit has no timestamp field, so records keeps a plain RangeIndex.
    row = summarize_activity(FIT_FILES / "DeveloperData.fit")
    assert row.total_elapsed_time is None
    assert row.total_distance is not None and row.total_distance > 0


def test_summarize_activity_leaves_distance_none_without_distance_column():
    # Plain GPX has no native per-point distance field, so there's no "distance" column.
    row = summarize_activity(GPX_FILES / "sample.gpx")
    assert row.total_distance is None
    assert row.total_elapsed_time is not None and row.total_elapsed_time > 0
