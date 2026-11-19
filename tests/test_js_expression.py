"""CQL → TriccOperation → CHT JavaScript for on-demand start.condition."""

from __future__ import annotations

import pytest

from tricc_oo.converters.cql_to_operation import transform_cql_to_operation
from tricc_oo.serializers.js_expression import render_cht_js_expression


def test_age_in_months_less_than():
    op = transform_cql_to_operation("AgeInMonths() < 60")
    assert op is not None
    js = render_cht_js_expression(op)
    assert "ageInMonths(contact)" in js
    assert "< 60" in js


def test_and_contact_field():
    op = transform_cql_to_operation("AgeInMonths() < 60 and sex = 'F'")
    assert op is not None
    js = render_cht_js_expression(op)
    assert "ageInMonths(contact)" in js
    assert "contact.sex" in js
    assert '"F"' in js
    assert "&&" in js


def test_unsupported_operator_fails():
    op = transform_cql_to_operation("Min({1, 2})")
    assert op is not None
    with pytest.raises(NotImplementedError, match="not supported"):
        render_cht_js_expression(op)
