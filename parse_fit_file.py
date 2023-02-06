"""Functions for parsing FIT files into Pandas DataFrames."""

import collections
import gzip
import os

import pandas as pd

import fitdecode


def copy_fit_frames(fit_file):
    """Yields FIT data frames from a file-like object."""

    processor = fitdecode.StandardUnitsDataProcessor()
    for frame in fitdecode.FitReader(fit_file, processor=processor):
        if (
            frame.frame_type == fitdecode.FIT_FRAME_DATA
            and frame.mesg_type is not None
        ):
            yield frame


def extract_fit_dicts(frames, name):
    """Yields dicts of frame data from FIT frames of a given name."""

    for frame in frames:
        if frame.name == name:
            yield dict(
                (field.name, field.value)
                for field in frame.fields
                if field.field is not None
            )


def parse_fit(file):
    """Loads a FIT activity into Pandas DataFrames.

    FIT frames and data fields that are marked as 'unknown' by fitdecode are
    dropped during import. Assumes that the FIT file is all one activity, i.e.
    chained FIT files will be merged into one set of return values.

    Args:
        file: File-like or path-like object. A path-like argument ending in
          '.gz' will be unzipped before processing.

    Returns:
        A tuple of (records, laps, extra).

        records: Time-indexed DataFrame of sensor data from the activity.
        laps: DataFrame of lap information from the activity.
        extra: Dict of additional information from the activity.
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
    records = records.set_index('timestamp')
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
