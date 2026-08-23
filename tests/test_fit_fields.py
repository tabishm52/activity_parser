"""Keeps fit_fields' generated unit tables covering the installed FIT profile."""

import pandas as pd
import pytest
from garmin_fit_sdk import Profile

from activity_parser.fit_fields import (
    LAP_UNITS,
    M_TO_KM,
    MPS_TO_KMH,
    RECORD_UNITS,
    SEMICIRCLES_TO_DEGREES,
    SESSION_UNITS,
    convert_units,
    convert_units_mapping,
)

# Excluded from unit conversion from m/s to km/h
VERTICAL_RATE_FIELDS = frozenset(
    {
        "ascent_rate",
        "avg_neg_vertical_speed",
        "avg_pos_vertical_speed",
        "avg_vam",
        "max_neg_vertical_speed",
        "max_pos_vertical_speed",
        "vertical_speed",
    }
)


def _field_units(field) -> list[str]:
    """Returns a profile field's units, which are a string or a list of them."""
    units = field.get("units")
    if isinstance(units, str):
        return [units]
    return units or []


def _message_units(message_name: str) -> dict[str, set[str]]:
    """Collects every unit each field name carries in one FIT message type."""
    message = next(m for m in Profile["messages"].values() if m["name"] == message_name)
    units: dict[str, set[str]] = {}

    def collect(field) -> None:
        units.setdefault(field["name"], set()).update(_field_units(field))
        for sub_field in field.get("sub_fields") or []:
            collect(sub_field)

    for field in message["fields"].values():
        collect(field)
    return units


def generate_table(message_name: str) -> dict[str, float]:
    """Rebuilds one of fit_fields' unit tables from the installed FIT profile."""
    table: dict[str, float] = {}
    for name, units in _message_units(message_name).items():
        # A field carrying several units is a packed composite, not a plain value.
        if len(units) != 1:
            continue
        unit = next(iter(units))
        if unit == "semicircles":
            table[name] = SEMICIRCLES_TO_DEGREES
        elif unit == "m/s" and name not in VERTICAL_RATE_FIELDS:
            table[name] = MPS_TO_KMH
        elif unit == "m" and name.endswith("distance"):
            table[name] = M_TO_KM
    return table


@pytest.mark.parametrize(
    ("message_name", "table"),
    [("record", RECORD_UNITS), ("lap", LAP_UNITS), ("session", SESSION_UNITS)],
    ids=lambda arg: arg if isinstance(arg, str) else "",
)
def test_table_covers_installed_profile(message_name, table):
    """Every field the profile requires must be in ``table`` with the right factor.

    Extra entries (from a newer or older profile) are fine; they can't affect what the
    installed SDK actually returns.
    """
    required = generate_table(message_name)
    assert {name: table.get(name) for name in required} == required


def test_vertical_rates_and_non_distance_meters_are_not_converted():
    for field in ("avg_vam", "avg_pos_vertical_speed"):
        assert field not in LAP_UNITS
    for field in ("altitude", "gps_accuracy", "cycle_length"):
        assert field not in RECORD_UNITS
    assert "total_ascent" not in LAP_UNITS
    # A packed composite carrying both m/s and m.
    assert "compressed_speed_distance" not in RECORD_UNITS


def test_convert_units_scales_only_listed_columns():
    df = pd.DataFrame({"speed": [10.0], "distance": [2000.0], "altitude": [100.0]})
    out = convert_units(df, RECORD_UNITS)
    assert out["speed"].iloc[0] == pytest.approx(36.0)
    assert out["distance"].iloc[0] == pytest.approx(2.0)
    assert out["altitude"].iloc[0] == 100.0


def test_convert_units_leaves_unlisted_and_non_numeric_columns_alone():
    df = pd.DataFrame(
        {
            "unknown_61": [1000.0],
            "doughnuts_earned": [3.0],
            "speed": [("slow", "fast")],
        }
    )
    out = convert_units(df, RECORD_UNITS)
    assert out["unknown_61"].iloc[0] == 1000.0
    assert out["doughnuts_earned"].iloc[0] == 3.0
    assert out["speed"].iloc[0] == ("slow", "fast")


def test_convert_units_keeps_missing_values_missing():
    df = pd.DataFrame({"speed": [10.0, None]})
    out = convert_units(df, RECORD_UNITS)
    assert out["speed"].iloc[0] == pytest.approx(36.0)
    assert pd.isna(out["speed"].iloc[1])


def test_convert_units_mapping_scales_listed_fields():
    row = {"total_distance": 5000.0, "avg_speed": 10.0, "sport": "cycling"}
    out = convert_units_mapping(row, SESSION_UNITS)
    assert out["total_distance"] == pytest.approx(5.0)
    assert out["avg_speed"] == pytest.approx(36.0)
    assert out["sport"] == "cycling"


def test_convert_units_mapping_ignores_absent_and_non_numeric_values():
    row = {"avg_speed": None, "max_speed": "unknown"}
    out = convert_units_mapping(row, SESSION_UNITS)
    assert out == row
    assert "total_distance" not in out
