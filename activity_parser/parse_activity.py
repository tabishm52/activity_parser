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

    Each instance of this class is a parser object that can be used to import
    FIT, GPX and TCX files into DataFrames. During parsing, the column names in
    the resulting DataFrames are normalized to a standard set of names to allow
    for more interchangeable use of DataFrames from the different activity file
    types.
    """

    def __init__(self, strict_xml: bool = False) -> None:
        """Initialize parser settings, selectors, and mappers.

        Args:
            strict_xml: If True, TCX/GPX XML parsing fails on malformed input.
                If False, parser recovery is enabled.
        """

        self.strict_xml = strict_xml

        # 'Selectors' specify the list and order of columns to be copied from
        # each DataFrame (records and laps for each file type), and 'mappers'
        # translate the imported column names into canonical names

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

        self.tcx_records_selector = [
            "LatitudeDegrees",
            "LongitudeDegrees",
            "AltitudeMeters",
            "DistanceKm",
            "Speed",
            "Cadence",
            "HeartRateBpm",
            "Watts",
        ]

        self.gpx_records_selector = [
            "lat",
            "lon",
            "ele",
            "cad",
            "hr",
            "power",
            "atemp",
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

        self.tcx_records_mapper = {
            "LatitudeDegrees": "latitude",
            "LongitudeDegrees": "longitude",
            "AltitudeMeters": "altitude",
            "DistanceKm": "distance",
            "Speed": "speed",
            "Cadence": "cadence",
            "HeartRateBpm": "heart_rate",
            "Watts": "power",
        }

        self.gpx_records_mapper = {
            "lat": "latitude",
            "lon": "longitude",
            "ele": "altitude",
            "cad": "cadence",
            "hr": "heart_rate",
            "power": "power",
            "atemp": "temperature",
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
            "TriggerMethod",
            "StartTime",
            "TotalTimeSeconds",
            "DistanceKm",
            "AvgSpeed",
            "MaximumSpeed",
            "Cadence",
            "MaxBikeCadence",
            "AverageHeartRateBpm",
            "MaximumHeartRateBpm",
            "AvgWatts",
            "MaxWatts",
            "Calories",
        ]

        # Just use the FIT names for lap data as canonical
        self.fit_laps_mapper = {}

        self.tcx_laps_mapper = {
            "TriggerMethod": "lap_trigger",
            "StartTime": "start_time",
            "TotalTimeSeconds": "total_elapsed_time",
            "DistanceKm": "total_distance",
            "AvgSpeed": "avg_speed",
            "MaximumSpeed": "max_speed",
            "Cadence": "avg_cadence",
            "MaxBikeCadence": "max_cadence",
            "AverageHeartRateBpm": "avg_heart_rate",
            "MaximumHeartRateBpm": "max_heart_rate",
            "AvgWatts": "avg_power",
            "MaxWatts": "max_power",
            "Calories": "total_calories",
        }

    def parse(
        self,
        file: str | PathLike[str] | IO[str] | IO[bytes],
        ext: str | None = None,
    ) -> tuple[pd.DataFrame, pd.DataFrame, dict[str, Any]]:
        """Loads a FIT, TCX or GPX activity into Pandas DataFrames.

        During import, column names in ``records`` and ``laps`` are
        normalized into a canonical set of names. Note this function does not
        guarantee that all canonical columns appear in the output, it only
        renames the columns that are present in the activity file.

        Args:
            file: File-like or path-like object. A path-like argument ending in
                '.gz' will be unzipped before processing.
            ext: String of value ``FIT``, ``TCX``, or ``GPX`` that specifies
                the file type. Must be provided if ``file`` is a file-like
                object. Optional if ``file`` is a path-like object (the file
                type will be inferred from the file name).

        Returns:
            Tuple containing records, laps, and selected extra metadata.
        """

        if ext is not None:
            ext_normalized = normalize_extension(ext)
        elif isinstance(file, (str, PathLike)):
            ext_normalized = infer_extension(file)
        else:
            raise ValueError(
                "ext must be provided when file is a file-like object."
            )

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
            records, laps, extra = parse_tcx(file, strict_xml=self.strict_xml)
            records = select_and_rename_cols(
                records,
                self.tcx_records_selector,
                self.tcx_records_mapper,
            )
            records.rename_axis("time", inplace=True)
            laps = select_and_rename_cols(
                laps,
                self.tcx_laps_selector,
                self.tcx_laps_mapper,
            )

        elif ext_normalized == "gpx":
            records, laps, extra = parse_gpx(file, strict_xml=self.strict_xml)
            records = select_and_rename_cols(
                records,
                self.gpx_records_selector,
                self.gpx_records_mapper,
            )
            records.rename_axis("time", inplace=True)
            # Note GPX files have no lap information

        else:
            raise ValueError(f"File type not supported: {ext_normalized}")

        return records, laps, extra
