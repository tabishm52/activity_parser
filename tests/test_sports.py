"""Tests for the TCX/GPX -> FIT sport vocabulary mapping."""

from garmin_fit_sdk import Profile

from activity_parser.sports import _STRAVA_SPORTS, _TCX_SPORTS, normalize_sport


def test_normalize_sport_passes_through_unrecognized_value():
    # No faithful FIT sport for these; they must not be guessed at.
    assert normalize_sport("Wheelchair") == "Wheelchair"


def test_normalize_sport_none_input():
    assert normalize_sport(None) is None


def test_alias_targets_are_valid_fit_sports():
    fit_sports = frozenset(Profile["types"]["sport"].values())
    for alias, target in {**_TCX_SPORTS, **_STRAVA_SPORTS}.items():
        assert target in fit_sports, f"{alias!r} maps to {target!r}, not a FIT sport"
