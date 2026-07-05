"""Class for parsing FIT, TCX and GPX files into Pandas DataFrames."""

from collections.abc import Mapping, Sequence
from os import PathLike
from pathlib import Path
from typing import IO, Any

import pandas as pd

from .parse_fit_file import parse_fit
from .parse_tcx_gpx import parse_gpx, parse_tcx


def select_and_rename_cols(
    df: pd.DataFrame,
    selector: Sequence[str],
    mapper: Mapping[str, str],
) -> pd.DataFrame:
    """Select and rename columns from a DataFrame."""
    cols = [col for col in selector if col in df.columns]
    return df.loc[:, cols].rename(columns=mapper)


def normalize_extension(ext: str) -> str:
    """Normalize an extension string to one of: fit, tcx, gpx."""
    normalized = ext.lower().lstrip(".")
    if normalized == "gz":
        raise ValueError("Ambiguous extension: .gz without base extension.")
    return normalized


def infer_extension(file: str | PathLike[str]) -> str:
    """Infer normalized extension from a path-like input."""
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
    """

    def __init__(self, strict_xml: bool = False) -> None:
        """Initialize parser settings, selectors, and mappers.

        Args:
            strict_xml: If True, TCX/GPX XML parsing fails on malformed input.
                If False, parser recovery is enabled.
        """
        self.strict_xml = strict_xml

        # 'Selectors' specify the list and order of columns to be copied from each
        # DataFrame (records and laps for each file type), and 'mappers' translate the
        # imported column names into canonical names

        self.fit_records_selector = [
            "position_lat",
            "position_long",
            "altitude",
            "distance",
            "speed",
            "cadence",
            "fractional_cadence",
            "heart_rate",
            "power",
            "left_right_balance",
            "accumulated_power",
            "temperature",
        ]

        # TCX/GPX records and laps are already canonically named by parse_tcx_gpx (see
        # xml_fields); these selectors just pick a stable column order and drop any
        # namespace-qualified columns for unrecognized elements.

        self.tcx_records_selector = [
            "latitude",
            "longitude",
            "altitude",
            "distance",
            "speed",
            "cadence",
            "cadence_sensor",
            "heart_rate",
            "power",
            "sensor_state",
        ]

        self.gpx_records_selector = [
            "latitude",
            "longitude",
            "altitude",
            "distance",
            "speed",
            "cadence",
            "heart_rate",
            "power",
            "temperature",
            "water_temperature",
            "depth",
            "course",
            "bearing",
            "satellites",
            "hdop",
            "vdop",
            "pdop",
            "fix_type",
            "sensor",
            "magnetic_variation",
            "geoid_height",
            "age_of_dgps_data",
            "dgps_station_id",
            "name",
            "cmt",
            "desc",
            "src",
            "sym",
            "type",
            "url",
            "urlname",
        ]

        self.fit_records_mapper = {
            "position_lat": "latitude",
            "position_long": "longitude",
            "altitude": "altitude",
            "distance": "distance",
            "speed": "speed",
            "cadence": "cadence",
            "fractional_cadence": "fractional_cadence",
            "heart_rate": "heart_rate",
            "power": "power",
            "left_right_balance": "left_right_balance",
            "accumulated_power": "accumulated_power",
            "temperature": "temperature",
        }

        self.fit_laps_selector = [
            "event",
            "event_type",
            "lap_trigger",
            "start_time",
            "total_elapsed_time",
            "total_timer_time",
            "start_position_lat",
            "start_position_long",
            "end_position_lat",
            "end_position_long",
            "total_distance",
            "total_ascent",
            "total_descent",
            "avg_vam",
            "avg_speed",
            "max_speed",
            "avg_cadence",
            "max_cadence",
            "avg_fractional_cadence",
            "max_fractional_cadence",
            "total_strokes",
            "avg_heart_rate",
            "max_heart_rate",
            "time_in_hr_zone",
            "avg_power",
            "max_power",
            "normalized_power",
            "left_right_balance",
            "time_in_power_zone",
            "total_work",
            "avg_temperature",
            "max_temperature",
            "total_calories",
            "total_fat_calories",
            "sport",
            "sub_sport",
        ]

        self.tcx_laps_selector = [
            "lap_trigger",
            "start_time",
            "total_elapsed_time",
            "total_distance",
            "avg_speed",
            "max_speed",
            "avg_cadence",
            "max_cadence",
            "total_strides",
            "avg_heart_rate",
            "max_heart_rate",
            "avg_power",
            "max_power",
            "total_calories",
            "intensity",
            "notes",
        ]

        # Just use the FIT names for lap data as canonical
        self.fit_laps_mapper = {}

    def parse(
        self,
        file: str | PathLike[str] | IO[bytes],
        ext: str | None = None,
    ) -> tuple[pd.DataFrame, pd.DataFrame, dict[str, Any]]:
        """Loads a FIT, TCX or GPX activity into Pandas DataFrames.

        During import, column names in ``records`` and ``laps`` are normalized into a
        canonical set of names. Note this function does not guarantee that all canonical
        columns appear in the output, it only renames the columns that are present in
        the activity file.

        Args:
            file: Binary file-like or path-like object. A path-like argument ending in
                ``.gz`` will be unzipped before processing.
            ext: File type, case-insensitive: ``fit``, ``tcx``, or ``gpx``. Required for
                a file-like ``file``; optional for a path-like ``file`` (inferred from
                the name).

        Returns:
            Tuple containing records, laps, and selected extra metadata.
        """
        if ext is not None:
            ext_normalized = normalize_extension(ext)
        elif isinstance(file, (str, PathLike)):
            ext_normalized = infer_extension(file)
        else:
            raise ValueError("ext must be provided when file is a file-like object.")

        if ext_normalized == "fit":
            records, laps, extra = parse_fit(file)
            records = select_and_rename_cols(
                records,
                self.fit_records_selector,
                self.fit_records_mapper,
            )
            records.rename_axis("time", inplace=True)
            laps = select_and_rename_cols(
                laps,
                self.fit_laps_selector,
                self.fit_laps_mapper,
            )

        elif ext_normalized == "tcx":
            # parse_tcx already emits canonically-named columns; these selectors just
            # pick a stable order and drop unrecognized-element columns.
            records, laps, extra = parse_tcx(file, strict_xml=self.strict_xml)
            records = select_and_rename_cols(records, self.tcx_records_selector, {})
            records.rename_axis("time", inplace=True)
            laps = select_and_rename_cols(laps, self.tcx_laps_selector, {})

        elif ext_normalized == "gpx":
            # parse_gpx already emits canonically-named columns; see tcx branch above.
            records, laps, extra = parse_gpx(file, strict_xml=self.strict_xml)
            records = select_and_rename_cols(records, self.gpx_records_selector, {})
            records.rename_axis("time", inplace=True)
            # Note GPX files have no lap information

        else:
            raise ValueError(f"File type not supported: {ext_normalized}")

        return records, laps, extra
