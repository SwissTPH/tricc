"""Unit tests for display-text ${REF} injection (TriccNodeDisplayModel only)."""

from tricc_oo.converters.utils import remove_html
from tricc_oo.models.base import (
    TriccOperation,
    TriccReference,
)
from tricc_oo.models.message import (
    TriccMessage,
    TriccMessageMark,
    TriccMessageMarkKind,
    TriccMessageText,
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


def _text_and_refs(message):
    texts = []
    refs = []
    for part in getattr(message, "children", []) or []:
        if isinstance(part, TriccMessageText):
            texts.append(part.value)
        elif isinstance(part, TriccReference):
            refs.append(part.value)
        elif isinstance(part, TriccMessageMark):
            t, r = _text_and_refs(TriccMessage(children=part.children))
            texts.extend(t)
            refs.extend(r)
        elif not isinstance(part, TriccMessageText):
            refs.append(getattr(part, "name", part))
    return texts, refs


class TestParseInjectionText:
    def test_no_tokens_unchanged(self):
        assert parse_injection_text("plain label") == "plain label"

    def test_single_ref(self):
        result = parse_injection_text("${age}")
        assert isinstance(result, TriccMessage)
        assert isinstance(result.children[0], TriccReference)
        assert result.children[0].value == "age"

    def test_concat_parts(self):
        result = parse_injection_text("Age is ${age} years")
        assert isinstance(result, TriccMessage)
        assert not isinstance(result, TriccOperation)
        texts, refs = _text_and_refs(result)
        assert texts == ["Age is ", " years"]
        assert refs == ["age"]

    def test_two_refs(self):
        result = parse_injection_text("${a} and ${b}")
        assert isinstance(result, TriccMessage)
        _, refs = _text_and_refs(result)
        assert refs == ["a", "b"]


class TestLoadDisplayText:
    def test_clean_then_parse(self):
        raw = "Age is <b>${age}</b> years"
        result = load_display_text(raw)
        assert isinstance(result, TriccMessage)
        assert not isinstance(result, TriccOperation)
        _, refs = _text_and_refs(result)
        assert refs == ["age"]
        md = serialize_injection_for_js_text(result)
        assert "<b>" not in md
        assert "</b>" not in md
        assert "**${age}**" in md

    def test_dict_locales(self):
        raw = {"en": "Hi ${name}", "fr": "Bonjour ${name}"}
        result = load_display_text(raw)
        assert isinstance(result["en"], TriccMessage)
        assert isinstance(result["fr"], TriccMessage)

    def test_no_tokens_still_cleaned(self):
        result = load_display_text("<b>Hello world</b>")
        assert isinstance(result, TriccMessage)
        assert serialize_injection_for_js_text(result) == "**Hello world**"

    def test_plain_string_unchanged(self):
        assert load_display_text("plain label") == "plain label"

    def test_strong_wraps_ref(self):
        result = load_display_text("<b>Give ${dose} mg</b>")
        assert isinstance(result, TriccMessage)
        assert len(result.children) == 1
        mark = result.children[0]
        assert isinstance(mark, TriccMessageMark)
        assert mark.kind == TriccMessageMarkKind.STRONG
        texts, refs = _text_and_refs(TriccMessage(children=mark.children))
        assert refs == ["dose"]
        assert texts == ["Give ", " mg"]
        assert serialize_injection_for_js_text(result) == "**Give ${dose} mg**"

    def test_html_not_markdownified_before_split(self):
        result = load_display_text("<b>${age}</b>")
        assert isinstance(result, TriccMessage)
        mark = result.children[0]
        assert isinstance(mark, TriccMessageMark)
        assert isinstance(mark.children[0], TriccReference)
        assert mark.children[0].value == "age"

    def test_no_space_short_label(self):
        result = load_display_text("<b>Yes</b>")
        assert serialize_injection_for_js_text(result) == "**Yes**"
        assert "<b>" not in serialize_injection_for_js_text(result)

    def test_get_references_walks_marks(self):
        result = load_display_text("<b>Give ${dose} mg</b> of ${drug}")
        refs = [r.value for r in result.get_references() if isinstance(r, TriccReference)]
        assert refs == ["dose", "drug"]

    def test_replace_node_updates_interp(self):
        result = load_display_text("Age is ${age}")
        age = TriccNodeInteger(id="age1", name="age", label="Age", activity=None, group=None)
        result.replace_node(TriccReference("age"), age)
        assert age in list(result.children)

    def test_markdown_no_trailing_newline(self):
        result = load_display_text("<b>Hello world</b>")
        actual = serialize_injection_for_js_text(result)
        assert actual == "**Hello world**"
        assert actual == actual.rstrip("\n")


class TestSerializeOdk:
    def test_concat_to_injection_string(self):
        msg = TriccMessage(
            children=[
                TriccMessageText(value="Age is "),
                TriccReference("age"),
                TriccMessageText(value=" years"),
            ]
        )
        assert serialize_injection_for_js_text(msg, get_export_name) == "Age is ${age} years"

    def test_resolved_node_uses_export_name(self):
        age = TriccNodeInteger(
            id="age1",
            name="age",
            label="Age",
            activity=None,
            group=None,
        )
        age.last = True
        msg = TriccMessage(
            children=[
                TriccMessageText(value="Age is "),
                age,
                TriccMessageText(value=" years"),
            ]
        )
        out = serialize_injection_for_js_text(msg)
        assert out.startswith("Age is ${")
        assert out.endswith("} years")
        assert "concat(" not in out


class TestGetNameLabel:
    def test_concat_uses_first_static_segment(self):
        from tricc_oo.models.base import label_text_for_name

        msg = TriccMessage(
            children=[
                TriccMessageText(value="Patient is "),
                TriccReference("age"),
                TriccMessageText(value=" years"),
            ]
        )
        assert label_text_for_name(msg) == "Patient is "
        note = TriccNodeNote(
            id="n1",
            name="note_age",
            label=msg,
            activity=None,
            group=None,
        )
        assert "Patient is " in note.get_name()
        assert "concatenate" not in note.get_name().lower()

    def test_concat_without_static_skips_label(self):
        from tricc_oo.models.base import label_text_for_name

        msg = TriccMessage(
            children=[TriccReference("age"), TriccReference("weight")]
        )
        assert label_text_for_name(msg) is None
        note = TriccNodeNote(
            id="n2",
            name="note_only_refs",
            label=msg,
            activity=None,
            group=None,
        )
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
        assert isinstance(note.label, TriccMessage)
        assert not isinstance(note.label, TriccOperation)

    def test_rhombus_label_not_converted_to_concatenate_injection(self):
        rh = TriccNodeRhombus(
            id="r1",
            name="rh1",
            label="has_symptom = true",
            reference="has_symptom",
            activity=None,
            group=None,
        )
        rh.label = "check ${age}"
        apply_display_text_injections(rh, clean_fn=remove_html)
        from tricc_oo.models.tricc import TriccNodeDisplayModel

        assert not isinstance(rh, TriccNodeDisplayModel)
        load_expressions(rh)
        assert isinstance(rh.label, str)
        assert "${age}" in rh.label

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
    def test_iter_node_dependencies_includes_label_refs(self):
        from tricc_oo.visitors.tricc import iter_node_dependencies

        note = TriccNodeNote(
            id="n1",
            name="note_age",
            label="Patient is ${age}",
            activity=None,
            group=None,
        )
        load_expressions(note)
        names = []
        for dep, etype in iter_node_dependencies(note):
            if etype == "ref":
                names.append(getattr(dep, "value", None) or getattr(dep, "name", None))
        assert "age" in names
    def test_resolve_note_label_ref(self):
        from tricc_oo.models.tricc import TriccNodeActivity, TriccNodeMainStart

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
        assert isinstance(note.label, TriccMessage)

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
        assert isinstance(note.label, TriccMessage)
        node_parts = [
            p for p in note.label.children if not isinstance(p, TriccMessageText)
        ]
        assert age in node_parts or any(
            getattr(p, "name", None) == "age" for p in node_parts
        )

        odk = serialize_injection_for_js_text(note.label)
        assert odk.startswith("Patient is ${")
        assert "concat(" not in odk
