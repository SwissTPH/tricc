"""A bare identifier is text, a reference is quoted (block spec §18.8 point 1, rev 2026-11-19).

Covers the parser rule, the TriccStatic / TriccReference split (siblings, not parent and
child) and the legacy rhombus whose tested value is a bare name.
"""

import logging

import pytest

from tricc_oo.converters.cql_to_operation import transform_cql_to_operation
from tricc_oo.converters.xml_to_tricc import TriccRhombusError, load_expressions
from tricc_oo.models.base import TriccOperation, TriccReference, TriccStatic
from tricc_oo.models.calculate import TriccNodeRhombus


def rhombus(reference, label):
    return TriccNodeRhombus(id="r1", name="rh1", label=label, reference=reference, activity=None, group=None)


class TestParser:
    def test_bare_identifier_is_text(self):
        assert transform_cql_to_operation("axillary") == TriccStatic("axillary")

    def test_quoted_identifier_is_a_reference(self):
        assert transform_cql_to_operation('"weight"') == TriccReference("weight")

    def test_reference_is_not_a_static(self):
        ref = TriccReference("weight")
        assert not isinstance(ref, TriccStatic)
        assert not isinstance(TriccStatic("weight"), TriccReference)
        assert ref != TriccStatic("weight") and TriccStatic("weight") != ref
        assert ref.copy() == ref and list(ref.get_references()) == [ref]
        assert not TriccStatic(1).get_references()


class TestRhombus:
    def test_quoted_reference(self):
        rh = rhombus('"weight"', "weight > 38?")
        load_expressions(rh)
        assert isinstance(rh.expression_reference, TriccOperation)
        assert rh.expression_reference.reference[0] == TriccReference("weight")

    def test_legacy_bare_name_is_quoted_with_a_warning(self, caplog):
        rh = rhombus("weight", "weight > 38?")
        with caplog.at_level(logging.WARNING):
            load_expressions(rh)
        # quoted, the name is a reference again and takes the label's condition
        assert isinstance(rh.expression_reference, TriccOperation)
        assert rh.expression_reference.reference[0] == TriccReference("weight")
        assert any("bare name" in r.getMessage() and '"weight"' in r.getMessage() for r in caplog.records)

    def test_cql_starting_with_a_literal_is_accepted(self):
        rh = rhombus('38 < "weight"', "Weight above 38")
        load_expressions(rh)
        assert isinstance(rh.expression_reference, TriccOperation)
        assert TriccReference("weight") in rh.expression_reference.reference

    def test_constant_that_is_no_name_fails(self):
        with pytest.raises(TriccRhombusError):
            load_expressions(rhombus("38", "Always"))
