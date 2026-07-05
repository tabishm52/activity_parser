"""Declarative field tables describing the TCX and GPX schemas.

Each table maps a path of ``(namespace, localname)`` steps from a record/lap element
down to a leaf attribute or element (see ``parse_tcx_gpx.walk_fields``) to a canonical
output column and a conversion. Leaf elements not present in a table still appear in
the output, namespace-qualified, as uncoerced strings (see
``parse_tcx_gpx.unknown_column_name``).

Canonical column names reuse FIT's vocabulary where an equivalent FIT field exists, so
the same name means the same unit regardless of source format.

When two entries share a canonical column (e.g. base ``Cadence`` and TPX
``RunCadence``), the value from whichever element occurs first in the document wins;
there's no explicit priority beyond document order.

Schemas transcribed from (retrieved 2026-07-04):
- TCX v2 / ActivityExtension v2: https://www8.garmin.com/xmlschemas/TrainingCenterDatabasev2.xsd
  and .../ActivityExtensionv2.xsd
- GPX 1.0 / 1.1: https://www.topografix.com/GPX/1/0/gpx.xsd and .../1/1/gpx.xsd
- Garmin TrackPointExtension v1 / v2: https://www8.garmin.com/xmlschemas/TrackPointExtensionv1.xsd
  and TrackPointExtensionv2.xsd
- Cluetrust GPXDATA: https://www.cluetrust.com/Schemas/gpxdata10.xsd
"""

from collections.abc import Callable, Mapping
from dataclasses import dataclass

import pandas as pd

TCX_NS = "http://www.garmin.com/xmlschemas/TrainingCenterDatabase/v2"
AEXT_NS = "http://www.garmin.com/xmlschemas/ActivityExtension/v2"
GPX10_NS = "http://www.topografix.com/GPX/1/0"
GPX11_NS = "http://www.topografix.com/GPX/1/1"
TPX1_NS = "http://www.garmin.com/xmlschemas/TrackPointExtension/v1"
TPX2_NS = "http://www.garmin.com/xmlschemas/TrackPointExtension/v2"
GPXDATA_NS = "http://www.cluetrust.com/XML/GPXDATA/1/0"

# A step is (namespace, localname); attributes are marked with a "@" localname prefix.
FieldPathStep = tuple[str | None, str]
FieldPath = tuple[FieldPathStep, ...]

Converter = Callable[[pd.Series], pd.Series]


def to_datetime(values: pd.Series) -> pd.Series:
    """Parses ISO8601 timestamps, tolerating a mix of naive and UTC-offset values."""
    # Without format="ISO8601", timestamps mixing naive and UTC-offset values in the
    # same column silently become NaT instead of parsing.
    return pd.to_datetime(values, errors="coerce", utc=True, format="ISO8601")


def _numeric_scale(factor: float) -> Converter:
    """Builds a converter: all-or-nothing numeric coercion, then scale by ``factor``."""

    def convert(values: pd.Series) -> pd.Series:
        non_null = values.notna().sum()
        if non_null == 0:
            return values

        numeric_values = pd.to_numeric(values, errors="coerce")
        if numeric_values.notna().sum() != non_null:
            # Some values genuinely aren't numeric; leave the column as raw strings
            # rather than partially coercing it.
            return values

        return numeric_values * factor

    return convert


# Conversion from meters and m/s to km and kph is done to align with processing done by
# fitdecode.StandardUnitsDataProcessor
NUMERIC: Converter = _numeric_scale(1.0)
NUMERIC_M_TO_KM: Converter = _numeric_scale(1 / 1000)
NUMERIC_MS_TO_KMH: Converter = _numeric_scale(3.6)


@dataclass(frozen=True)
class XmlField:
    """A known schema field: its canonical output column and value conversion.

    ``convert`` is ``None`` for fields kept as raw strings.
    """

    column: str
    convert: Converter | None = None


def column_converts(fields: Mapping[FieldPath, XmlField]) -> dict[str, Converter | None]:
    """Maps each canonical column produced by ``fields`` to its conversion."""
    converts: dict[str, Converter | None] = {}
    for field in fields.values():
        converts.setdefault(field.column, field.convert)
    return converts


def _prefixed(
    prefix: FieldPath, ns: str, fields: Mapping[tuple[str, ...], XmlField]
) -> dict[FieldPath, XmlField]:
    """Qualify bare-localname paths with a namespace and attach them under a prefix."""
    return {prefix + tuple((ns, step) for step in path): field for path, field in fields.items()}


def _wpt_base_fields(ns: str) -> dict[FieldPath, XmlField]:
    """Fields shared by GPX 1.0 and 1.1's ``wptType`` (used for ``trkpt``)."""
    return {
        ((None, "@lat"),): XmlField("latitude", NUMERIC),
        ((None, "@lon"),): XmlField("longitude", NUMERIC),
        ((ns, "ele"),): XmlField("altitude", NUMERIC),
        ((ns, "time"),): XmlField("time", to_datetime),
        ((ns, "fix"),): XmlField("fix_type"),
        ((ns, "sat"),): XmlField("satellites", NUMERIC),
        ((ns, "hdop"),): XmlField("hdop", NUMERIC),
        ((ns, "vdop"),): XmlField("vdop", NUMERIC),
        ((ns, "pdop"),): XmlField("pdop", NUMERIC),
        ((ns, "ageofdgpsdata"),): XmlField("age_of_dgps_data", NUMERIC),
        ((ns, "dgpsid"),): XmlField("dgps_station_id", NUMERIC),
        ((ns, "magvar"),): XmlField("magnetic_variation", NUMERIC),
        ((ns, "geoidheight"),): XmlField("geoid_height", NUMERIC),
        # Descriptive base-schema strings; rare on trackpoints but schema-legal.
        # <link> is omitted: it's a structured element, not a leaf value.
        ((ns, "name"),): XmlField("name"),
        ((ns, "cmt"),): XmlField("cmt"),
        ((ns, "desc"),): XmlField("desc"),
        ((ns, "src"),): XmlField("src"),
        ((ns, "sym"),): XmlField("sym"),
        ((ns, "type"),): XmlField("type"),
    }


# ---------------------------------------------------------------------------
# TCX: Trackpoint_t (base) + ActivityExtension/v2 TPX
# ---------------------------------------------------------------------------

TCX_TRACKPOINT_FIELDS: dict[FieldPath, XmlField] = {
    ((TCX_NS, "Time"),): XmlField("time", to_datetime),
    ((TCX_NS, "Position"), (TCX_NS, "LatitudeDegrees")): XmlField("latitude", NUMERIC),
    ((TCX_NS, "Position"), (TCX_NS, "LongitudeDegrees")): XmlField("longitude", NUMERIC),
    ((TCX_NS, "AltitudeMeters"),): XmlField("altitude", NUMERIC),
    ((TCX_NS, "DistanceMeters"),): XmlField("distance", NUMERIC_M_TO_KM),
    ((TCX_NS, "HeartRateBpm"), (TCX_NS, "Value")): XmlField("heart_rate", NUMERIC),
    ((TCX_NS, "Cadence"),): XmlField("cadence", NUMERIC),
    ((TCX_NS, "SensorState"),): XmlField("sensor_state"),
    # ActivityExtension/v2 TPX (CadenceSensor is an attribute of the TPX element)
    ((TCX_NS, "Extensions"), (AEXT_NS, "TPX"), (None, "@CadenceSensor")): XmlField(
        "cadence_sensor"
    ),
    ((TCX_NS, "Extensions"), (AEXT_NS, "TPX"), (AEXT_NS, "Speed")): XmlField(
        "speed", NUMERIC_MS_TO_KMH
    ),
    ((TCX_NS, "Extensions"), (AEXT_NS, "TPX"), (AEXT_NS, "RunCadence")): XmlField(
        "cadence", NUMERIC
    ),
    ((TCX_NS, "Extensions"), (AEXT_NS, "TPX"), (AEXT_NS, "Watts")): XmlField("power", NUMERIC),
}

# ---------------------------------------------------------------------------
# TCX: ActivityLap_t (base) + ActivityExtension/v2 LX
# ---------------------------------------------------------------------------

TCX_LAP_FIELDS: dict[FieldPath, XmlField] = {
    ((None, "@StartTime"),): XmlField("start_time", to_datetime),
    ((TCX_NS, "TotalTimeSeconds"),): XmlField("total_elapsed_time", NUMERIC),
    ((TCX_NS, "DistanceMeters"),): XmlField("total_distance", NUMERIC_M_TO_KM),
    ((TCX_NS, "MaximumSpeed"),): XmlField("max_speed", NUMERIC_MS_TO_KMH),
    ((TCX_NS, "Calories"),): XmlField("total_calories", NUMERIC),
    ((TCX_NS, "AverageHeartRateBpm"), (TCX_NS, "Value")): XmlField("avg_heart_rate", NUMERIC),
    ((TCX_NS, "MaximumHeartRateBpm"), (TCX_NS, "Value")): XmlField("max_heart_rate", NUMERIC),
    ((TCX_NS, "Intensity"),): XmlField("intensity"),
    ((TCX_NS, "Cadence"),): XmlField("avg_cadence", NUMERIC),
    ((TCX_NS, "TriggerMethod"),): XmlField("lap_trigger"),
    ((TCX_NS, "Notes"),): XmlField("notes"),
    # ActivityExtension/v2 LX
    ((TCX_NS, "Extensions"), (AEXT_NS, "LX"), (AEXT_NS, "AvgSpeed")): XmlField(
        "avg_speed", NUMERIC_MS_TO_KMH
    ),
    ((TCX_NS, "Extensions"), (AEXT_NS, "LX"), (AEXT_NS, "MaxBikeCadence")): XmlField(
        "max_cadence", NUMERIC
    ),
    ((TCX_NS, "Extensions"), (AEXT_NS, "LX"), (AEXT_NS, "AvgRunCadence")): XmlField(
        "avg_cadence", NUMERIC
    ),
    ((TCX_NS, "Extensions"), (AEXT_NS, "LX"), (AEXT_NS, "MaxRunCadence")): XmlField(
        "max_cadence", NUMERIC
    ),
    # Reusing FIT's "total_strides" name for Garmin's running step count.
    ((TCX_NS, "Extensions"), (AEXT_NS, "LX"), (AEXT_NS, "Steps")): XmlField(
        "total_strides", NUMERIC
    ),
    ((TCX_NS, "Extensions"), (AEXT_NS, "LX"), (AEXT_NS, "AvgWatts")): XmlField(
        "avg_power", NUMERIC
    ),
    ((TCX_NS, "Extensions"), (AEXT_NS, "LX"), (AEXT_NS, "MaxWatts")): XmlField(
        "max_power", NUMERIC
    ),
}

# ---------------------------------------------------------------------------
# GPX: wptType (base, both 1.0/1.1) + TrackPointExtension v1/v2 + gpxdata + bare <power>
# ---------------------------------------------------------------------------

_TPX_COMMON_FIELDS = {
    ("TrackPointExtension", "atemp"): XmlField("temperature", NUMERIC),
    ("TrackPointExtension", "wtemp"): XmlField("water_temperature", NUMERIC),
    ("TrackPointExtension", "depth"): XmlField("depth", NUMERIC),
    ("TrackPointExtension", "hr"): XmlField("heart_rate", NUMERIC),
    ("TrackPointExtension", "cad"): XmlField("cadence", NUMERIC),
}
# v1 has no speed/course/bearing; v2 adds them.
_TPX_V2_ONLY_FIELDS = {
    ("TrackPointExtension", "speed"): XmlField("speed", NUMERIC_MS_TO_KMH),
    ("TrackPointExtension", "course"): XmlField("course", NUMERIC),
    ("TrackPointExtension", "bearing"): XmlField("bearing", NUMERIC),
}

_GPXDATA_FIELDS = {
    ("hr",): XmlField("heart_rate", NUMERIC),
    ("cadence",): XmlField("cadence", NUMERIC),
    ("temp",): XmlField("temperature", NUMERIC),
    ("distance",): XmlField("distance", NUMERIC_M_TO_KM),
    ("sensor",): XmlField("sensor"),
}

_GPX11_EXTENSIONS_PREFIX: FieldPath = ((GPX11_NS, "extensions"),)

GPX_TRACKPOINT_FIELDS: dict[FieldPath, XmlField] = {
    **_wpt_base_fields(GPX10_NS),
    **_wpt_base_fields(GPX11_NS),
    # GPX 1.0 exposes speed/course/url/urlname directly on trkpt; 1.1 dropped them in
    # favor of extensions and <link>.
    ((GPX10_NS, "course"),): XmlField("course", NUMERIC),
    ((GPX10_NS, "speed"),): XmlField("speed", NUMERIC_MS_TO_KMH),
    ((GPX10_NS, "url"),): XmlField("url"),
    ((GPX10_NS, "urlname"),): XmlField("urlname"),
    # Strava writes a bare, un-namespaced <power> inside <extensions>; it inherits
    # GPX's default namespace since it has no prefix of its own.
    (*_GPX11_EXTENSIONS_PREFIX, (GPX11_NS, "power")): XmlField("power", NUMERIC),
    **_prefixed(_GPX11_EXTENSIONS_PREFIX, TPX1_NS, _TPX_COMMON_FIELDS),
    **_prefixed(_GPX11_EXTENSIONS_PREFIX, TPX2_NS, {**_TPX_COMMON_FIELDS, **_TPX_V2_ONLY_FIELDS}),
    **_prefixed(_GPX11_EXTENSIONS_PREFIX, GPXDATA_NS, _GPXDATA_FIELDS),
}
