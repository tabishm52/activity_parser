"""Walks a directory and parses every activity file in parallel.

FIT decoding and XML parsing are both CPU-bound, so a process pool is a real speedup
despite the cost of pickling arguments and results across process boundaries.
"""

from collections.abc import Callable, Iterator
from concurrent.futures import ProcessPoolExecutor, as_completed
from pathlib import Path
from typing import TypeVar

T = TypeVar("T")

ACTIVITY_EXTENSIONS = ("FIT", "TCX", "GPX")


def activity_file_type(path: Path) -> str | None:
    """Returns ``path``'s activity file type (``FIT``, ``TCX``, or ``GPX``), if any.

    Detection is suffix-based and case-insensitive, since device exports commonly use
    uppercase extensions (e.g. Garmin's ``.FIT``) and others lowercase. A ``.gz``
    wrapper is looked through. The returned type is always upper case, for reports.

    Args:
        path: Path to inspect. Not required to exist.

    Returns:
        The file type, or ``None`` if ``path`` doesn't match a known activity type.
    """
    ext = path.suffix.upper().lstrip(".")
    if ext == "GZ":
        ext = Path(path.stem).suffix.upper().lstrip(".")

    return ext if ext in ACTIVITY_EXTENSIONS else None


def find_activity_files(directory: Path) -> list[Path]:
    """Recursively finds (possibly gzipped) FIT/TCX/GPX files under ``directory``.

    Args:
        directory: Directory to search recursively.

    Returns:
        Matching paths, sorted for deterministic ordering.
    """
    path_list = [
        path for path in directory.rglob("*") if path.is_file() and activity_file_type(path)
    ]

    return sorted(path_list)


def parse_directory(directory: Path, task: Callable[[Path], T]) -> Iterator[tuple[Path, T]]:
    """Runs ``task`` over every activity file under ``directory`` in a process pool.

    If ``task`` raises, that exception propagates and ends the run. In most cases, it
    makes sense for ``task`` to catch and handle any ``ParseError`` exceptions in the
    files it processes.

    Args:
        directory: Directory to search recursively, via ``find_activity_files``.
        task: Function called with each path in a worker process. Must be a plain
            module-level function, so that ``ProcessPoolExecutor`` can pickle it by
            qualified name.

    Returns:
        An iterator of ``(path, result)``, yielded in completion order.
    """
    with ProcessPoolExecutor() as pool:
        paths = find_activity_files(directory)
        futures = {pool.submit(task, path): path for path in paths}

        for future in as_completed(futures):
            yield futures[future], future.result()
