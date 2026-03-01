"""Functions for parsing FIT files into Pandas DataFrames."""

import collections
import gzip
import os
from collections.abc import Iterable, Iterator
from typing import Any, BinaryIO

import pandas as pd

import fitdecode


def copy_fit_frames(fit_file: BinaryIO) -> Iterator[Any]:
    """Yields FIT data frames from a file-like object."""

    processor = fitdecode.StandardUnitsDataProcessor()
    for frame in fitdecode.FitReader(fit_file, processor=processor):
        if (
            frame.frame_type == fitdecode.FIT_FRAME_DATA
            and frame.mesg_type is not None
        ):
            yield frame


def extract_fit_dicts(
    frames: Iterable[Any],
    name: str,
) -> Iterator[dict[str, Any]]:
    """Yields dicts of frame data from FIT frames of a given name."""

    for frame in frames:
        if frame.name == name:
            yield dict(
                (field.name, field.value)
                for field in frame.fields
                if field.field is not None
            )


def parse_fit(
    file: str | os.PathLike[str] | BinaryIO,
) -> tuple[pd.DataFrame, pd.DataFrame, dict[str, Any]]:
    """Loads a FIT activity into Pandas DataFrames.

    FIT frames and data fields that are marked as 'unknown' by fitdecode are
    dropped during import. Assumes that the FIT file is all one activity, i.e.
    chained FIT files will be merged into one set of return values.

    Args:
        file: File-like or path-like object. A path-like argument ending in
            '.gz' will be unzipped before processing.

    Returns:
        Tuple containing records, laps, and additional metadata.
    """

    try:
        _, ext = os.path.splitext(file)
        is_path = True
    except TypeError:
        is_path = False

    if is_path:
        if ext.lower() == '.gz':
            with gzip.open(file) as fit_file:
                frames = list(copy_fit_frames(fit_file))
        else:
            with open(file, 'rb') as fit_file:
                frames = list(copy_fit_frames(fit_file))
    else:
        frames = list(copy_fit_frames(file))

    # Note FIT files occasionally have duplicate timestamps, just drop those
    records = pd.DataFrame(extract_fit_dicts(frames, 'record'))
    if 'timestamp' in records.columns:
        records = records.set_index('timestamp')
    else:
        records.index = pd.Index(records.index, name='timestamp')
    records = records[~records.index.duplicated()]

    laps = pd.DataFrame(extract_fit_dicts(frames, 'lap'))

    names = collections.Counter(frame.name for frame in frames)
    names.pop('record', None)
    names.pop('lap', None)

    extra = {}
    for name, count in names.items():
        if count == 1:
            extra[name] = next(extract_fit_dicts(frames, name))
        else:
            extra[name] = pd.DataFrame(extract_fit_dicts(frames, name))

    return records, laps, extra
