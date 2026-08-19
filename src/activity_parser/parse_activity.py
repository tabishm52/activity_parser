"""Class for parsing FIT, TCX and GPX files into Pandas DataFrames."""

from collections.abc import Sequence
from os import PathLike
from pathlib import Path
from typing import IO

import pandas as pd

from .output import DEFAULT_LAP_COLUMNS, DEFAULT_RECORD_COLUMNS, Activity
from .parse_fit_file import parse_fit
from .parse_tcx_gpx import parse_gpx, parse_tcx


def select_and_reorder_cols(
    df: pd.DataFrame,
    columns: Sequence[str],
    include_all_columns: bool,
) -> pd.DataFrame:
    """Selects and reorders df's columns.

    Columns from ``columns`` present in ``df`` are selected, in that order; columns
    absent from ``df`` are omitted.

    If ``include_all_columns`` is True, any of ``df``'s remaining columns not in
    ``columns`` are appended afterward, in their original order.
    """
    present = [col for col in columns if col in df.columns]
    if include_all_columns:
        selected = set(columns)
        extra = [col for col in df.columns if col not in selected]
        ordered = present + extra
    else:
        ordered = present
    return df.loc[:, ordered]


def normalize_extension(ext: str) -> str:
    """Lowercases an extension string and strips any leading dot, raising ``ValueError``
    for a bare ``gz``.
    """
    normalized = ext.lower().lstrip(".")
    if normalized == "gz":
        raise ValueError("Ambiguous extension: .gz without base extension.")
    return normalized


def infer_extension(file: str | PathLike[str]) -> str:
    """Infers normalized extension from a path-like input."""
    p = Path(file)
    ext = p.suffix
    if ext.lower() == ".gz":
        ext = Path(p.stem).suffix
    return normalize_extension(ext)


class ActivityParser:
    """Parser for FIT, GPX and TCX files.

    Each instance of this class is a parser object that can be used to import FIT, GPX
    and TCX files into DataFrames. During parsing, the column names in the resulting
    DataFrames are normalized to a standard set of names to allow for more
    interchangeable use of DataFrames from the different activity file types.

    The output of ``parse`` is controlled by ``record_columns`` and ``lap_columns``,
    initialized on each instance from ``DEFAULT_RECORD_COLUMNS`` and
    ``DEFAULT_LAP_COLUMNS``. Reassign or mutate them to select different columns.
    """

    def __init__(
        self,
        *,
        include_all_columns: bool = False,
        check_crc: bool = False,
        strict_xml: bool = False,
    ) -> None:
        """Initialize parser settings and column lists.

        Args:
            include_all_columns: If True, ``parse`` returns all parsed columns. If
                False, ``parse`` returns only the columns in ``record_columns`` and
                ``lap_columns``.
            check_crc: If True, ``parse`` verifies CRC integrity of FIT files. If
                False, CRC verification is skipped.
            strict_xml: If True, ``parse`` requires well-formed TCX/GPX XML. If False,
                parser recovery is enabled.
        """
        self.record_columns: list[str] = list(DEFAULT_RECORD_COLUMNS)
        self.lap_columns: list[str] = list(DEFAULT_LAP_COLUMNS)
        self.include_all_columns = include_all_columns
        self.check_crc = check_crc
        self.strict_xml = strict_xml

    def parse(
        self,
        file: str | PathLike[str] | IO[bytes],
        ext: str | None = None,
    ) -> tuple[pd.DataFrame, pd.DataFrame, Activity]:
        """Loads a FIT, TCX or GPX activity into Pandas DataFrames.

        Output columns come from ``record_columns``/``lap_columns``, plus any extra
        columns if ``include_all_columns`` is set. Not all columns are guaranteed to
        appear, only those present in the activity file.

        Args:
            file: Binary file-like or path-like object. A path-like argument ending in
                ``.gz`` will be unzipped before processing.
            ext: File type, case-insensitive: ``fit``, ``tcx``, or ``gpx``. Required for
                a file-like ``file``; optional for a path-like ``file`` (inferred from
                the name).

        Returns:
            Tuple containing records, laps, and an ``Activity`` summary. GPX files have
            no lap information, so laps is empty for them.

        Raises:
            ParseError: The file fails to parse (``FitError`` for FIT, ``XmlError`` for
                TCX/GPX).
            ValueError: The file's type can't be determined, or isn't one of ``fit``,
                ``tcx``, ``gpx``.
        """
        if ext is not None:
            ext_normalized = normalize_extension(ext)
        elif isinstance(file, (str, PathLike)):
            ext_normalized = infer_extension(file)
        else:
            raise ValueError("ext must be provided when file is a file-like object.")

        if ext_normalized == "fit":
            records, laps, activity = parse_fit(file, check_crc=self.check_crc)

        elif ext_normalized == "tcx":
            records, laps, activity = parse_tcx(file, strict_xml=self.strict_xml)

        elif ext_normalized == "gpx":
            # Note GPX files have no lap information; laps is always empty.
            records, laps, activity = parse_gpx(file, strict_xml=self.strict_xml)

        else:
            raise ValueError(f"File type not supported: {ext_normalized}")

        records = select_and_reorder_cols(records, self.record_columns, self.include_all_columns)
        records.rename_axis("time", inplace=True)
        laps = select_and_reorder_cols(laps, self.lap_columns, self.include_all_columns)

        return records, laps, activity
