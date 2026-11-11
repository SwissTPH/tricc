"""Block calls: expression arguments, abstract concepts, outputs, stored data.

feature/20261111-block-params-and-start-node.md §18.8 (frontend RFC tricc-frontend#12).
"""

import inspect
import json
import re

import pytest
import yaml

from tricc_oo.converters.cql_to_operation import FUNCTION_MAP, stored_data_functions
from tricc_oo.converters.xml_to_tricc import parse_expression
from tricc_oo.models.params import (
    DYNAMIC,
    E_ARG_DYNAMIC_STATIC,
    E_BLOCK_PRIVATE,
    E_BLOCK_SCOPE,
    E_OUTPUT_UNKNOWN,
    EXPRESSION,
    TEXT,
    CallSite,
    ParamSpec,
    Template,
    TriccParamError,
    bind,
    compute_static_only,
    substitute,
)
from tests.test_block_params import copy_fixture, edit_yaml, load, node, survey


def spec(name, ptype, **kw):
    return ParamSpec(name=name, type=ptype, owner="page", **kw)


def add_age(block):
    """The block takes the child's age and shows a note for older children."""
    block["params"].append({"name": "age", "type": "number", "required": True})
    block["nodes"].insert(-1, {"id": "mt-old", "type": "note", "name": "older_{{site}}",
                               "label": "Age {{age}} days", "relevance": "{{age}} > 60"})
    block["edges"] = [e for e in block["edges"] if not (e["source"] == "mt-f" and e["target"] == "mt-e")]
    block["edges"] += [{"source": "mt-f", "target": "mt-old"}, {"source": "mt-old", "target": "mt-e"}]


AGE_ARG = {"expression": "AgeInDays()", "intent": {"en": "Age of the child in days"}}


# ---------------------------------------------------------------------------
# Stored-data functions (§18.8 point 4)
# ---------------------------------------------------------------------------


class TestStoredDataFunctions:
    def test_shape(self):
        from tricc_oo.converters.cql_to_operation import STORED_DATA_FUNCTIONS_FILE

        data = json.load(open(STORED_DATA_FUNCTIONS_FILE, encoding="utf-8"))
        assert data["version"] == 1
        assert {f["reads"] for f in data["functions"]} == {"patient", "encounter", "history", "context"}

    def test_every_function_is_known(self):
        from tricc_oo.converters.fhir import populate_helper, repeat_helper

        source = inspect.getsource(repeat_helper) + inspect.getsource(populate_helper)
        defined = set(re.findall(r"define function \"?(\w+)", source)) | set(FUNCTION_MAP)
        assert set(stored_data_functions()) <= defined

    @pytest.mark.parametrize("name", sorted(stored_data_functions()))
    def test_parser_flags_each(self, name):
        op = parse_expression("", f"{name}('code') > 1")
        assert op.get_stored_data()

    @pytest.mark.parametrize("cql", ["Today() > 1", "Now() > 1", '"weight" > 2', "Round(1.5) = 2"])
    def test_not_stored_data(self, cql):
        assert not parse_expression("", cql).get_stored_data()


# ---------------------------------------------------------------------------
# Expression arguments (§18.8 point 1)
# ---------------------------------------------------------------------------


class TestExpressionArguments:
    def test_bind_calls_add_dynamic(self):
        seen = []
        env = bind({"age": spec("age", "number")}, {"age": {"expression": "AgeInDays()"}}, {}, "use",
                   add_dynamic=lambda name, arg, caller_env: seen.append(arg) or "arg_age_x")
        assert env["age"][1] == {DYNAMIC: "arg_age_x"}
        assert seen == [{"expression": "AgeInDays()"}]

    def test_rendering(self):
        env = {"age": (spec("age", "number"), {DYNAMIC: "arg_age_x"})}
        assert substitute("{{age}} > 60", env, EXPRESSION, "w") == '"arg_age_x" > 60'
        assert substitute("Age {{age}}", env, TEXT, "w") == "Age ${arg_age_x}"
        with pytest.raises(TriccParamError) as err:
            substitute('"x_{{age|raw}}"', env, EXPRESSION, "w")
        assert err.value.code == E_ARG_DYNAMIC_STATIC

    def test_passed_on_bound_never_inherited(self):
        caller = {"age": (spec("age", "number"), {DYNAMIC: "arg_age_x"})}
        params = {"age": spec("age", "number")}
        # passed on by {{age}}: the same calculate, not evaluated again
        assert bind(params, {"age": "{{age}}"}, caller, "use")["age"][1] == {DYNAMIC: "arg_age_x"}
        # not inherited by name
        assert bind(params, {}, caller, "use")["age"][1] is None

    @pytest.mark.parametrize("ptype", ["name", "concept"])
    def test_static_only_types(self, ptype):
        with pytest.raises(TriccParamError) as err:
            bind({"p": spec("p", ptype)}, {"p": {"expression": "1"}}, {}, "use", add_dynamic=lambda *a: "c")
        assert err.value.code == E_ARG_DYNAMIC_STATIC

    def test_intervention_arguments_are_fixed(self):
        with pytest.raises(TriccParamError) as err:
            bind({"p": spec("p", "number")}, {"p": {"expression": "1"}}, {}, "intervention")
        assert err.value.code == E_ARG_DYNAMIC_STATIC

    def test_static_only_through_the_chain(self):
        inner = Template(id="inner", is_block=True, declared={"s": spec("s", "string")}, static_used=["s"])
        mid = Template(id="mid", is_block=True, declared={"t": spec("t", "string")},
                       calls=[CallSite(caller="mid", node_id="c1", link="inner", kind="block", args={"s": "{{t}}"})])
        top = Template(id="top", calls=[
            CallSite(caller="top", node_id="c2", link="mid", kind="block", args={}),
            CallSite(caller="top", node_id="c3", link="inner", kind="block", args={"s": "x_{{u}}"}),
        ], static_used=["u"])
        static = compute_static_only({t.id: t for t in (inner, mid, top)}, lambda c: c.link)
        assert static["mid"] == {"t"}
        assert static["top"] == {"t", "u"}  # t: inherited by the call that leaves it out

    def test_project(self, tmp_path):
        root = copy_fixture(tmp_path)
        edit_yaml(root / "blocks" / "measure-temperature.block.yaml", add_age)
        edit_yaml(root / "activities" / "triage.activity.yaml",
                  lambda d: [node(d, n)["args"].update(age=AGE_ARG) for n in ("t-ax", "t-re")])
        # AgeInDays() needs an output that knows the patient's age
        edit_yaml(root / "tricc.yaml", lambda d: d.update(output_strategies=["XLSFormCDSSStrategy"]))
        rows = survey(root)
        args = sorted(n for n in rows if n.startswith("arg_age_"))
        assert len(args) == 2  # one calculate per use, evaluated at the use
        for name in args:
            assert rows[name]["type"] == "calculate" and rows[name]["calculation"]
        relevances = {rows["older_axillary"]["relevance"], rows["older_rectal"]["relevance"]}
        assert all(any(f"${{{a}}}" in r for a in args) and ">60" in r.replace(" ", "") for r in relevances)

    def test_dynamic_for_a_name_parameter_fails(self, tmp_path):
        root = copy_fixture(tmp_path)
        edit_yaml(root / "activities" / "triage.activity.yaml",
                  lambda d: node(d, "t-ax")["args"].update(site={"expression": "'axillary'"}))
        with pytest.raises(TriccParamError) as err:
            load(root)
        assert err.value.code == E_ARG_DYNAMIC_STATIC
        assert "t-ax" in str(err.value) and "site" in str(err.value)

    def test_intervention_expression_fails(self, tmp_path):
        root = copy_fixture(tmp_path)
        edit_yaml(root / "tricc.yaml",
                  lambda d: d["interventions"][0]["args"].update(lab_available={"expression": "true"}))
        with pytest.raises(TriccParamError) as err:
            load(root)
        assert err.value.code == E_ARG_DYNAMIC_STATIC


# ---------------------------------------------------------------------------
# Stored data inside a block (§18.1, §18.8 decisions)
# ---------------------------------------------------------------------------


class TestBlockScope:
    def block_with(self, relevance):
        def change(block):
            block["nodes"].insert(-1, {"id": "mt-x", "type": "note", "name": "x_{{site}}", "label": "X",
                                       "relevance": relevance})
            block["edges"] = [e for e in block["edges"] if e["target"] != "mt-e" or e["source"] != "mt-f"]
            block["edges"] += [{"source": "mt-f", "target": "mt-x"}, {"source": "mt-x", "target": "mt-e"}]
        return change

    def test_age_inside_a_block_fails(self, tmp_path):
        root = copy_fixture(tmp_path)
        edit_yaml(root / "blocks" / "measure-temperature.block.yaml", self.block_with("AgeInDays() > 60"))
        with pytest.raises(TriccParamError) as err:
            load(root)
        assert err.value.code == E_BLOCK_SCOPE

    def test_today_is_allowed(self, tmp_path):
        root = copy_fixture(tmp_path)
        edit_yaml(root / "blocks" / "measure-temperature.block.yaml", self.block_with("Today() > 1"))
        load(root)


# ---------------------------------------------------------------------------
# Outputs (§18.8 point 3)
# ---------------------------------------------------------------------------


class TestOutputs:
    def test_no_key_every_field_is_an_output(self, tmp_path):
        assert {"temp_axillary", "temp_rectal"} <= set(survey(copy_fixture(tmp_path)))

    def test_listed_output_keeps_its_name(self, tmp_path):
        root = copy_fixture(tmp_path)
        edit_yaml(root / "blocks" / "measure-temperature.block.yaml", lambda d: d.update(outputs=["temp_{{site}}"]))
        assert {"temp_axillary", "temp_rectal"} <= set(survey(root))

    def test_empty_list_makes_fields_private(self, tmp_path):
        root = copy_fixture(tmp_path)
        edit_yaml(root / "blocks" / "measure-temperature.block.yaml", lambda d: d.update(outputs=[]))
        rows = survey(root)
        assert "temp_axillary" not in rows
        private = [n for n in rows if n.startswith("temp_axillary_")]
        assert len(private) == 1
        # the block's own decision follows the private name
        assert private[0] in rows["fever_axillary"]["relevance"]

    def test_two_uses_have_their_own_private_fields(self, tmp_path):
        root = copy_fixture(tmp_path)
        edit_yaml(root / "blocks" / "measure-temperature.block.yaml", lambda d: d.update(outputs=[]))
        edit_yaml(root / "activities" / "triage.activity.yaml",
                  lambda d: node(d, "t-re").update(args={"site": "axillary"}))
        rows = survey(root)
        assert len([n for n in rows if n.startswith("temp_axillary_")]) == 2

    def test_private_read_from_outside_fails(self, tmp_path):
        root = copy_fixture(tmp_path)
        edit_yaml(root / "blocks" / "measure-temperature.block.yaml", lambda d: d.update(outputs=[]))
        edit_yaml(root / "activities" / "triage.activity.yaml",
                  lambda d: node(d, "t-lab").update(relevance='"temp_axillary" > 37'))
        with pytest.raises(TriccParamError) as err:
            load(root)
        assert err.value.code == E_BLOCK_PRIVATE
        assert "temp_axillary" in str(err.value)

    def test_unknown_output_fails(self, tmp_path):
        root = copy_fixture(tmp_path)
        edit_yaml(root / "blocks" / "measure-temperature.block.yaml", lambda d: d.update(outputs=["nope"]))
        with pytest.raises(TriccParamError) as err:
            load(root)
        assert err.value.code == E_OUTPUT_UNKNOWN


# ---------------------------------------------------------------------------
# Abstract concepts (§18.8 point 2)
# ---------------------------------------------------------------------------

TERMINOLOGY = {
    "resourceType": "CodeSystem", "id": "proj", "name": "proj", "title": "Project", "status": "draft",
    "content": "complete",
    "url": "http://example.org/proj",
    "concept": [
        {
            "code": "temp_{{site}}", "display": "Temperature ({{site}})",
            "designation": [{"language": "fr", "value": "Température ({{site}})"}],
            "property": [
                {"code": "notSelectable", "valueBoolean": True},
                {"code": "kind", "valueCode": "template"},
                {"code": "owner", "valueCode": "measure-temperature"},
                {"code": "dataType", "valueCode": "decimal"},
            ],
        },
        {"code": "axillary", "display": "Axillary", "designation": [{"language": "fr", "value": "Axillaire"}]},
    ],
}


def load_with_terminology(root):
    from tricc_oo.models.project_config import TriccProjectConfig
    from tricc_oo.runner import load_input_project, read_input_file_contents

    (root / "terminology").mkdir()
    (root / "terminology" / "proj.json").write_text(json.dumps(TERMINOLOGY), encoding="utf-8")
    config = TriccProjectConfig(**yaml.safe_load((root / "tricc.yaml").read_text(encoding="utf-8")))
    files = [str(root / "activities" / "triage.activity.yaml"), str(root / "blocks" / "measure-temperature.block.yaml")]
    return load_input_project(
        [("YamlStrategy", files, read_input_file_contents(files))], str(root / "media"), config,
        config.interventions[0], terminology=[("proj.json", json.dumps(TERMINOLOGY))],
    )


class TestAbstractConcepts:
    def concepts(self, project):
        return {c.code: c for cs in project.code_systems.values() for c in cs.concept or []}

    def test_each_use_gets_a_concrete_concept(self, tmp_path):
        concepts = self.concepts(load_with_terminology(copy_fixture(tmp_path)))
        axillary = concepts["temp_axillary"]
        # a choice renders as its option's label, in each language; a code without concept as is
        assert axillary.display == "Temperature (Axillary)"
        assert [d.value for d in axillary.designation] == ["Température (Axillaire)"]
        assert concepts["temp_rectal"].display == "Temperature (rectal)"
        assert [p.code for p in axillary.property] == ["dataType"]
        assert concepts["temp_axillary"].id != concepts["temp_{{site}}"].id

    def test_project_concrete_concept_wins(self, tmp_path):
        global TERMINOLOGY
        saved = TERMINOLOGY
        TERMINOLOGY = json.loads(json.dumps(saved))
        TERMINOLOGY["concept"].append({"code": "temp_rectal", "display": "Rectal temperature"})
        try:
            concepts = self.concepts(load_with_terminology(copy_fixture(tmp_path)))
        finally:
            TERMINOLOGY = saved
        assert concepts["temp_rectal"].display == "Rectal temperature"

    def test_never_exported(self, tmp_path):
        from tricc_oo.converters.codesystem_to_ocl import transform_fhir_to_ocl
        from tricc_oo.strategies.input.base_input_strategy import BaseInputStrategy

        project = load_with_terminology(copy_fixture(tmp_path))
        media = tmp_path / "out" / "media"
        media.mkdir(parents=True)
        BaseInputStrategy.write_terminology(project, str(media))
        written = json.loads((tmp_path / "out" / "proj_codesystem.json").read_text(encoding="utf-8"))
        codes = {c["code"] for c in written["concept"]}
        assert "temp_{{site}}" not in codes and "temp_axillary" in codes
        payload = transform_fhir_to_ocl(TERMINOLOGY, "proj", "me", "User")
        assert "temp_{{site}}" not in {p.get("id") for p in payload if isinstance(p, dict)}
        assert "temp_{{site}}" not in json.dumps([getattr(p, "id", None) for p in payload])

    def test_selected_outside_its_block_fails(self, tmp_path):
        from tricc_oo.models.params import E_ABSTRACT_SELECTED
        from tricc_oo.strategies.input.yaml import YamlStrategy

        project = load_with_terminology(copy_fixture(tmp_path))
        with pytest.raises(TriccParamError) as err:
            YamlStrategy._resolve_concept("temp_{{site}}", None, project, "node n")
        assert err.value.code == E_ABSTRACT_SELECTED


# ---------------------------------------------------------------------------
# draw.io
# ---------------------------------------------------------------------------


class TestDrawio:
    def test_expression_argument(self, tmp_path):
        from tests.test_block_params import DRAWIO, drawio_survey

        text = open(DRAWIO, encoding="utf-8").read()
        text = text.replace('param.site="choice(axillary|rectal)!"',
                            'param.site="choice(axillary|rectal)!" param.age="number!"')
        text = text.replace('param.site="axillary"',
                            'param.site="axillary" param.age="{&quot;expression&quot;:&quot;Round(40.2)&quot;}"')
        text = text.replace('param.site="rectal"', 'param.site="rectal" param.age="{{lab_available}}"')
        with pytest.raises(TriccParamError):  # a boolean passed to a number
            drawio_survey(tmp_path, text)
        text = text.replace('param.age="{{lab_available}}"', 'param.age="{&quot;expression&quot;:&quot;1&quot;}"')
        rows = drawio_survey(tmp_path / "ok", text)
        assert len([n for n in rows if n.startswith("arg_age_")]) == 2

    def test_outputs_attribute(self, tmp_path):
        from tests.test_block_params import DRAWIO, drawio_survey

        text = open(DRAWIO, encoding="utf-8").read()
        text = text.replace('odk_type="block_start"', 'odk_type="block_start" outputs="[]"')
        rows = drawio_survey(tmp_path, text)
        assert "temp_axillary" not in rows
        assert [n for n in rows if n.startswith("temp_axillary_")]
