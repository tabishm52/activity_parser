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

from collections.abc import Mapping
from dataclasses import dataclass
from enum import Enum, auto

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


class Convert(Enum):
    """How a leaf value should be coerced once collected into a DataFrame column."""

    STRING = auto()
    NUMERIC = auto()
    NUMERIC_M_TO_KM = auto()
    NUMERIC_MS_TO_KMH = auto()
    DATETIME = auto()


@dataclass(frozen=True)
class XmlField:
    """A known schema field: its canonical output column and value conversion."""

    column: str
    convert: Convert = Convert.STRING


def column_converts(fields: Mapping[FieldPath, XmlField]) -> dict[str, Convert]:
    """Maps each canonical column produced by ``fields`` to its conversion."""
    converts: dict[str, Convert] = {}
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
        ((None, "@lat"),): XmlField("latitude", Convert.NUMERIC),
        ((None, "@lon"),): XmlField("longitude", Convert.NUMERIC),
        ((ns, "ele"),): XmlField("altitude", Convert.NUMERIC),
        ((ns, "time"),): XmlField("time", Convert.DATETIME),
        ((ns, "fix"),): XmlField("fix_type", Convert.STRING),
        ((ns, "sat"),): XmlField("satellites", Convert.NUMERIC),
        ((ns, "hdop"),): XmlField("hdop", Convert.NUMERIC),
        ((ns, "vdop"),): XmlField("vdop", Convert.NUMERIC),
        ((ns, "pdop"),): XmlField("pdop", Convert.NUMERIC),
        ((ns, "ageofdgpsdata"),): XmlField("age_of_dgps_data", Convert.NUMERIC),
        ((ns, "dgpsid"),): XmlField("dgps_station_id", Convert.NUMERIC),
        ((ns, "magvar"),): XmlField("magnetic_variation", Convert.NUMERIC),
        ((ns, "geoidheight"),): XmlField("geoid_height", Convert.NUMERIC),
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
    ((TCX_NS, "Time"),): XmlField("time", Convert.DATETIME),
    ((TCX_NS, "Position"), (TCX_NS, "LatitudeDegrees")): XmlField("latitude", Convert.NUMERIC),
    ((TCX_NS, "Position"), (TCX_NS, "LongitudeDegrees")): XmlField("longitude", Convert.NUMERIC),
    ((TCX_NS, "AltitudeMeters"),): XmlField("altitude", Convert.NUMERIC),
    ((TCX_NS, "DistanceMeters"),): XmlField("distance", Convert.NUMERIC_M_TO_KM),
    ((TCX_NS, "HeartRateBpm"), (TCX_NS, "Value")): XmlField("heart_rate", Convert.NUMERIC),
    ((TCX_NS, "Cadence"),): XmlField("cadence", Convert.NUMERIC),
    ((TCX_NS, "SensorState"),): XmlField("sensor_state"),
    # ActivityExtension/v2 TPX (CadenceSensor is an attribute of the TPX element)
    ((TCX_NS, "Extensions"), (AEXT_NS, "TPX"), (None, "@CadenceSensor")): XmlField(
        "cadence_sensor"
    ),
    ((TCX_NS, "Extensions"), (AEXT_NS, "TPX"), (AEXT_NS, "Speed")): XmlField(
        "speed", Convert.NUMERIC_MS_TO_KMH
    ),
    ((TCX_NS, "Extensions"), (AEXT_NS, "TPX"), (AEXT_NS, "RunCadence")): XmlField(
        "cadence", Convert.NUMERIC
    ),
    ((TCX_NS, "Extensions"), (AEXT_NS, "TPX"), (AEXT_NS, "Watts")): XmlField(
        "power", Convert.NUMERIC
    ),
}

# ---------------------------------------------------------------------------
# TCX: ActivityLap_t (base) + ActivityExtension/v2 LX
# ---------------------------------------------------------------------------

TCX_LAP_FIELDS: dict[FieldPath, XmlField] = {
    ((None, "@StartTime"),): XmlField("start_time", Convert.DATETIME),
    ((TCX_NS, "TotalTimeSeconds"),): XmlField("total_elapsed_time", Convert.NUMERIC),
    ((TCX_NS, "DistanceMeters"),): XmlField("total_distance", Convert.NUMERIC_M_TO_KM),
    ((TCX_NS, "MaximumSpeed"),): XmlField("max_speed", Convert.NUMERIC_MS_TO_KMH),
    ((TCX_NS, "Calories"),): XmlField("total_calories", Convert.NUMERIC),
    ((TCX_NS, "AverageHeartRateBpm"), (TCX_NS, "Value")): XmlField(
        "avg_heart_rate", Convert.NUMERIC
    ),
    ((TCX_NS, "MaximumHeartRateBpm"), (TCX_NS, "Value")): XmlField(
        "max_heart_rate", Convert.NUMERIC
    ),
    ((TCX_NS, "Intensity"),): XmlField("intensity"),
    ((TCX_NS, "Cadence"),): XmlField("avg_cadence", Convert.NUMERIC),
    ((TCX_NS, "TriggerMethod"),): XmlField("lap_trigger"),
    ((TCX_NS, "Notes"),): XmlField("notes"),
    # ActivityExtension/v2 LX
    ((TCX_NS, "Extensions"), (AEXT_NS, "LX"), (AEXT_NS, "AvgSpeed")): XmlField(
        "avg_speed", Convert.NUMERIC_MS_TO_KMH
    ),
    ((TCX_NS, "Extensions"), (AEXT_NS, "LX"), (AEXT_NS, "MaxBikeCadence")): XmlField(
        "max_cadence", Convert.NUMERIC
    ),
    ((TCX_NS, "Extensions"), (AEXT_NS, "LX"), (AEXT_NS, "AvgRunCadence")): XmlField(
        "avg_cadence", Convert.NUMERIC
    ),
    ((TCX_NS, "Extensions"), (AEXT_NS, "LX"), (AEXT_NS, "MaxRunCadence")): XmlField(
        "max_cadence", Convert.NUMERIC
    ),
    # Reusing FIT's "total_strides" name for Garmin's running step count.
    ((TCX_NS, "Extensions"), (AEXT_NS, "LX"), (AEXT_NS, "Steps")): XmlField(
        "total_strides", Convert.NUMERIC
    ),
    ((TCX_NS, "Extensions"), (AEXT_NS, "LX"), (AEXT_NS, "AvgWatts")): XmlField(
        "avg_power", Convert.NUMERIC
    ),
    ((TCX_NS, "Extensions"), (AEXT_NS, "LX"), (AEXT_NS, "MaxWatts")): XmlField(
        "max_power", Convert.NUMERIC
    ),
}

# ---------------------------------------------------------------------------
# GPX: wptType (base, both 1.0/1.1) + TrackPointExtension v1/v2 + gpxdata + bare <power>
# ---------------------------------------------------------------------------

_TPX_COMMON_FIELDS = {
    ("TrackPointExtension", "atemp"): XmlField("temperature", Convert.NUMERIC),
    ("TrackPointExtension", "wtemp"): XmlField("water_temperature", Convert.NUMERIC),
    ("TrackPointExtension", "depth"): XmlField("depth", Convert.NUMERIC),
    ("TrackPointExtension", "hr"): XmlField("heart_rate", Convert.NUMERIC),
    ("TrackPointExtension", "cad"): XmlField("cadence", Convert.NUMERIC),
}
# v1 has no speed/course/bearing; v2 adds them.
_TPX_V2_ONLY_FIELDS = {
    ("TrackPointExtension", "speed"): XmlField("speed", Convert.NUMERIC_MS_TO_KMH),
    ("TrackPointExtension", "course"): XmlField("course", Convert.NUMERIC),
    ("TrackPointExtension", "bearing"): XmlField("bearing", Convert.NUMERIC),
}

_GPXDATA_FIELDS = {
    ("hr",): XmlField("heart_rate", Convert.NUMERIC),
    ("cadence",): XmlField("cadence", Convert.NUMERIC),
    ("temp",): XmlField("temperature", Convert.NUMERIC),
    ("distance",): XmlField("distance", Convert.NUMERIC_M_TO_KM),
    ("sensor",): XmlField("sensor"),
}

_GPX11_EXTENSIONS_PREFIX: FieldPath = ((GPX11_NS, "extensions"),)

GPX_TRACKPOINT_FIELDS: dict[FieldPath, XmlField] = {
    **_wpt_base_fields(GPX10_NS),
    **_wpt_base_fields(GPX11_NS),
    # GPX 1.0 exposes speed/course/url/urlname directly on trkpt; 1.1 dropped them in
    # favor of extensions and <link>.
    ((GPX10_NS, "course"),): XmlField("course", Convert.NUMERIC),
    ((GPX10_NS, "speed"),): XmlField("speed", Convert.NUMERIC_MS_TO_KMH),
    ((GPX10_NS, "url"),): XmlField("url"),
    ((GPX10_NS, "urlname"),): XmlField("urlname"),
    # Strava writes a bare, un-namespaced <power> inside <extensions>; it inherits
    # GPX's default namespace since it has no prefix of its own.
    (*_GPX11_EXTENSIONS_PREFIX, (GPX11_NS, "power")): XmlField("power", Convert.NUMERIC),
    **_prefixed(_GPX11_EXTENSIONS_PREFIX, TPX1_NS, _TPX_COMMON_FIELDS),
    **_prefixed(_GPX11_EXTENSIONS_PREFIX, TPX2_NS, {**_TPX_COMMON_FIELDS, **_TPX_V2_ONLY_FIELDS}),
    **_prefixed(_GPX11_EXTENSIONS_PREFIX, GPXDATA_NS, _GPXDATA_FIELDS),
}
