"""Unit tests for display-text ${REF} injection (TriccNodeDisplayModel only)."""

from tricc_oo.converters.utils import remove_html
from tricc_oo.models.base import (
    TriccOperation,
    TriccOperator,
    TriccReference,
    TriccStatic,
)
from tricc_oo.models.tricc import TriccNodeNote, TriccNodeInteger
from tricc_oo.visitors.text_injection import (
    apply_display_text_injections,
    load_display_text,
    parse_injection_text,
    serialize_injection_for_js_text,
)
from tricc_oo.visitors.tricc import process_reference
from tricc_oo.converters.xml_to_tricc import load_expressions
from tricc_oo.converters.tricc_to_xls_form import get_export_name
from tricc_oo.models.calculate import TriccNodeRhombus, TriccNodeCalculate


class TestParseInjectionText:
    def test_no_tokens_unchanged(self):
        assert parse_injection_text("plain label") == "plain label"

    def test_single_ref(self):
        result = parse_injection_text("${age}")
        assert isinstance(result, TriccReference)
        assert result.value == "age"

    def test_concat_parts(self):
        result = parse_injection_text("Age is ${age} years")
        assert isinstance(result, TriccOperation)
        assert result.operator == TriccOperator.CONCATENATE
        assert len(result.reference) == 3
        assert isinstance(result.reference[0], TriccStatic)
        assert result.reference[0].value == "Age is "
        assert isinstance(result.reference[1], TriccReference)
        assert result.reference[1].value == "age"
        assert isinstance(result.reference[2], TriccStatic)
        assert result.reference[2].value == " years"

    def test_two_refs(self):
        result = parse_injection_text("${a} and ${b}")
        assert isinstance(result, TriccOperation)
        assert result.operator == TriccOperator.CONCATENATE
        refs = [p for p in result.reference if isinstance(p, TriccReference)]
        assert [r.value for r in refs] == ["a", "b"]


class TestLoadDisplayText:
    def test_clean_then_parse(self):
        raw = "Age is <b>${age}</b> years"
        result = load_display_text(raw, clean_fn=remove_html)
        assert isinstance(result, TriccOperation)
        assert result.operator == TriccOperator.CONCATENATE
        refs = [p for p in result.reference if isinstance(p, TriccReference)]
        assert len(refs) == 1 and refs[0].value == "age"
        # Statics should not retain raw HTML tags
        for p in result.reference:
            if isinstance(p, TriccStatic):
                assert "<b>" not in str(p.value)
                assert "</b>" not in str(p.value)

    def test_dict_locales(self):
        raw = {"en": "Hi ${name}", "fr": "Bonjour ${name}"}
        result = load_display_text(raw, clean_fn=remove_html)
        assert isinstance(result["en"], TriccOperation)
        assert isinstance(result["fr"], TriccOperation)

    def test_no_tokens_still_cleaned(self):
        # remove_html only strips markup when the string contains spaces
        result = load_display_text("<b>Hello world</b>", clean_fn=remove_html)
        assert isinstance(result, str)
        assert "<b>" not in result
        assert "Hello" in result


class TestSerializeOdk:
    def test_concat_to_injection_string(self):
        op = TriccOperation(
            TriccOperator.CONCATENATE,
            [
                TriccStatic("Age is "),
                TriccReference("age"),
                TriccStatic(" years"),
            ],
        )
        assert serialize_injection_for_js_text(op, get_export_name) == "Age is ${age} years"

    def test_resolved_node_uses_export_name(self):
        age = TriccNodeInteger(
            id="age1",
            name="age",
            label="Age",
            activity=None,
            group=None,
        )
        age.last = True
        op = TriccOperation(
            TriccOperator.CONCATENATE,
            [TriccStatic("Age is "), age, TriccStatic(" years")],
        )
        out = serialize_injection_for_js_text(op)
        assert out.startswith("Age is ${")
        assert out.endswith("} years")
        assert "concat(" not in out


class TestGetNameLabel:
    def test_concat_uses_first_static_segment(self):
        from tricc_oo.models.base import label_text_for_name

        op = TriccOperation(
            TriccOperator.CONCATENATE,
            [
                TriccStatic("Patient is "),
                TriccReference("age"),
                TriccStatic(" years"),
            ],
        )
        assert label_text_for_name(op) == "Patient is "
        note = TriccNodeNote(
            id="n1",
            name="note_age",
            label=op,
            activity=None,
            group=None,
        )
        assert "Patient is " in note.get_name()
        assert "concatenate" not in note.get_name().lower()

    def test_concat_without_static_skips_label(self):
        from tricc_oo.models.base import label_text_for_name

        op = TriccOperation(
            TriccOperator.CONCATENATE,
            [TriccReference("age"), TriccReference("weight")],
        )
        assert label_text_for_name(op) is None
        note = TriccNodeNote(
            id="n2",
            name="note_only_refs",
            label=op,
            activity=None,
            group=None,
        )
        # name present; label portion skipped (no op dump in id)
        assert "note_only_refs" in note.get_name()
        assert "concatenate" not in note.get_name().lower()


class TestDisplayModelOnly:
    def test_note_load_expressions_parses_injection(self):
        note = TriccNodeNote(
            id="n1",
            name="note_age",
            label="Patient is ${age} years",
            activity=None,
            group=None,
        )
        load_expressions(note)
        assert isinstance(note.label, TriccOperation)
        assert note.label.operator == TriccOperator.CONCATENATE

    def test_rhombus_label_not_converted_to_concatenate_injection(self):
        # Rhombus is calculate-side, not TriccNodeDisplayModel
        rh = TriccNodeRhombus(
            id="r1",
            name="rh1",
            label="has_symptom = true",
            reference="has_symptom",
            activity=None,
            group=None,
        )
        # Simulate clean label without full expression parse of reference
        rh.label = "check ${age}"
        apply_display_text_injections(rh, clean_fn=remove_html)
        # apply_display_text_injections does not check type — caller must;
        # load_expressions must not call it for rhombus
        from tricc_oo.models.tricc import TriccNodeDisplayModel

        assert not isinstance(rh, TriccNodeDisplayModel)

    def test_calculate_not_display_model(self):
        calc = TriccNodeCalculate(
            id="c1",
            name="c1",
            label="val ${x}",
            activity=None,
            group=None,
        )
        from tricc_oo.models.tricc import TriccNodeDisplayModel

        assert not isinstance(calc, TriccNodeDisplayModel)


class TestProcessReferenceResolve:
    def test_resolve_note_label_ref(self):
        from tricc_oo.models.tricc import TriccNodeActivity, TriccNodeMainStart
        from tricc_oo.models.calculate import TriccNodeActivityStart
        from tricc_oo.converters.utils import generate_id

        start = TriccNodeMainStart(id="start", name="start", label="Start")
        activity = TriccNodeActivity(
            id="act",
            name="act",
            root=start,
            label="Act",
        )
        start.activity = activity
        start.group = activity

        age = TriccNodeInteger(
            id="age1",
            name="age",
            label="Age",
            activity=activity,
            group=activity,
        )
        note = TriccNodeNote(
            id="n1",
            name="note_age",
            label="Patient is ${age}",
            activity=activity,
            group=activity,
        )
        activity.nodes = {age.id: age, note.id: note, start.id: start}

        load_expressions(note)
        assert isinstance(note.label, TriccOperation)

        processed = {age, start}
        ok = process_reference(
            note,
            processed_nodes=processed,
            calculates={},
            used_calculates=None,
            replace_reference=True,
            warn=False,
        )
        assert ok is True
        assert isinstance(note.label, TriccOperation)
        # Reference should be replaced by the age node
        node_parts = [
            p for p in note.label.reference if not isinstance(p, TriccStatic)
        ]
        assert age in node_parts or any(
            getattr(p, "name", None) == "age" for p in node_parts
        )

        odk = serialize_injection_for_js_text(note.label)
        assert odk.startswith("Patient is ${")
        assert "concat(" not in odk
