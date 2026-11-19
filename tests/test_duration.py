"""UCUM time subset used by intervention start.due / window."""

from __future__ import annotations

import pytest

from tricc_oo.converters.duration import parse_duration, to_days, to_fhir_duration


def test_parse_duration_units():
    assert parse_duration("30 s") == 30
    assert parse_duration("90 min") == 90 * 60
    assert parse_duration("12 h") == 12 * 3600
    assert parse_duration("3 d") == 3 * 86400
    assert parse_duration("2 wk") == 2 * 7 * 86400
    assert parse_duration("6 mo") == 6 * 30 * 86400


def test_parse_duration_rejects_years_and_unknown():
    with pytest.raises(ValueError, match="not allowed"):
        parse_duration("1 a")
    with pytest.raises(ValueError, match="not allowed"):
        parse_duration("2 kg")
    with pytest.raises(ValueError, match="not a UCUM"):
        parse_duration("soon")


def test_to_days_rounds_up():
    assert to_days(0) == 0
    assert to_days(86400) == 1
    assert to_days(86401) == 2


def test_fhir_duration_picks_largest_unit():
    assert to_fhir_duration(3 * 86400)["code"] == "d"
    assert to_fhir_duration(3 * 86400)["value"] == 3
    assert to_fhir_duration(90 * 60)["code"] == "min"
    assert to_fhir_duration(90 * 60)["value"] == 90
    assert to_fhir_duration(6 * 30 * 86400)["code"] == "mo"
