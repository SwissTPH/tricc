"""Block and activity parameters (feature/20261102-block-params-and-start-node.md, phases 1-5)."""

import glob
import os
import shutil

import pandas as pd
import pytest
import yaml

from tricc_oo.converters.xml_to_tricc import parse_expression
from tricc_oo.models.base import TriccOperator
from tricc_oo.models.params import (
    E_BLOCK_CYCLE,
    E_PARAM_CONFLICT,
    E_PARAM_REQUIRED,
    E_PARAM_TYPE,
    E_PARAM_UNKNOWN,
    EXPRESSION,
    TEXT,
    CallSite,
    ParamSpec,
    Template,
    TriccParamError,
    bind,
    compute_effective,
    parse_param_shorthand,
    substitute,
    unreferenced,
)
from tricc_oo.models.project_config import TriccProjectConfig
from tricc_oo.runner import load_input_project, read_input_file_contents, run_project_build

FIXTURE = os.path.join(os.path.dirname(__file__), "data", "projects", "block_params")


def spec(name, ptype, **kw):
    return ParamSpec(name=name, type=ptype, owner="page", **kw)


# ---------------------------------------------------------------------------
# Declarations and values
# ---------------------------------------------------------------------------


class TestDeclaration:
    def test_shorthand(self):
        site = parse_param_shorthand("site", "choice(axillary|rectal|oral)!")
        assert (site.type, site.options, site.required) == ("choice", ["axillary", "rectal", "oral"], True)
        assert parse_param_shorthand("threshold", "number=37.5").default == 37.5
        assert parse_param_shorthand("rectal", "boolean=false").default is False

    def test_json(self):
        note = parse_param_shorthand("note", '{"type":"string","description":"Free text"}')
        assert (note.type, note.description) == ("string", "Free text")

    @pytest.mark.parametrize(
        "ptype,options,value",
        [("choice", ["a", "b"], "c"), ("number", None, "abc"), ("boolean", None, "yes"), ("name", None, "Bad-Name")],
    )
    def test_type_mismatch(self, ptype, options, value):
        with pytest.raises(TriccParamError) as err:
            bind({"p": spec("p", ptype, options=options)}, {"p": value}, {}, "use")
        assert err.value.code == E_PARAM_TYPE

    def test_choice_needs_options(self):
        with pytest.raises(ValueError):
            spec("p", "choice")


# ---------------------------------------------------------------------------
# Placeholders
# ---------------------------------------------------------------------------


class TestPlaceholders:
    def env(self, **values):
        types = {
            "site": spec("site", "choice", options=["axillary", "rectal"]),
            "threshold": spec("threshold", "number"),
            "lab": spec("lab", "boolean"),
            "t": spec("t", "expression"),
            "c": spec("c", "concept"),
        }
        return {k: (types[k], v) for k, v in values.items()}

    def test_string_quoted_in_expression_raw_in_text(self):
        env = self.env(site="axillary")
        assert substitute("{{site}} = 'x'", env, EXPRESSION, "w") == "'axillary' = 'x'"
        assert substitute("Temperature ({{site}})", env, TEXT, "w") == "Temperature (axillary)"
        assert substitute('"temp_{{site|raw}}" > 1', env, EXPRESSION, "w") == '"temp_axillary" > 1'

    def test_literals(self):
        env = self.env(threshold=37.5, lab=True, c={"system": None, "code": "body_temperature"})
        assert substitute("{{threshold}}", env, EXPRESSION, "w") == "37.5"
        assert substitute("{{lab}}", env, EXPRESSION, "w") == "true"
        assert substitute("{{c}}", env, EXPRESSION, "w") == '"body_temperature"'

    def test_expression_is_parenthesized(self):
        rendered = substitute("{{t}} * 2", self.env(t='"a" + "b"'), EXPRESSION, "w")
        op = parse_expression("", rendered)
        assert op.operator == TriccOperator.MULTIPLIED
        first = op.reference[0]
        assert first.operator == TriccOperator.PARENTHESIS
        assert first.reference[0].operator == TriccOperator.PLUS

    def test_unknown_placeholder(self):
        with pytest.raises(TriccParamError) as err:
            substitute("{{nope}}", {}, TEXT, "w")
        assert err.value.code == E_PARAM_UNKNOWN

    def test_expression_not_in_text(self):
        with pytest.raises(TriccParamError):
            substitute("{{t}}", self.env(t="1 + 1"), TEXT, "w")


# ---------------------------------------------------------------------------
# Effective parameters and binding
# ---------------------------------------------------------------------------


def templates(*items):
    return {t.id: t for t in items}


def resolve_in(tpls):
    return lambda call: call.link if call.link in tpls else None


class TestEffective:
    def test_unbound_callee_param_bubbles_up(self):
        block = Template(id="b", is_block=True, declared={"site": spec("site", "string", required=True)})
        page = Template(id="p", calls=[CallSite(caller="p", node_id="n", link="b", kind="block")])
        tpls = templates(block, page)
        assert set(compute_effective(tpls, resolve_in(tpls))["p"]) == {"site"}

    def test_literal_binds_ref_renames(self):
        block = Template(id="b", is_block=True, declared={"site": spec("site", "string")})
        lit = Template(id="p1", calls=[CallSite(caller="p1", node_id="n", link="b", kind="block", args={"site": "x"})])
        ref = Template(id="p2", calls=[CallSite(caller="p2", node_id="n", link="b", kind="block",
                                                args={"site": "{{where}}"})])
        tpls = templates(block, lit, ref)
        eff = compute_effective(tpls, resolve_in(tpls))
        assert eff["p1"] == {}
        assert set(eff["p2"]) == {"where"} and eff["p2"]["where"].type == "string"

    def test_conflict(self):
        block = Template(id="b", is_block=True, declared={"site": spec("site", "string")})
        page = Template(id="p", declared={"site": spec("site", "number")},
                        calls=[CallSite(caller="p", node_id="n", link="b", kind="block")])
        tpls = templates(block, page)
        with pytest.raises(TriccParamError) as err:
            compute_effective(tpls, resolve_in(tpls))
        assert err.value.code == E_PARAM_CONFLICT

    def test_unknown_argument(self):
        block = Template(id="b", is_block=True)
        page = Template(id="p", calls=[CallSite(caller="p", node_id="n", link="b", kind="block", args={"x": 1})])
        tpls = templates(block, page)
        with pytest.raises(TriccParamError) as err:
            compute_effective(tpls, resolve_in(tpls))
        assert err.value.code == E_PARAM_UNKNOWN

    def test_block_cycle(self):
        a = Template(id="a", is_block=True, calls=[CallSite(caller="a", node_id="n", link="b", kind="block")])
        b = Template(id="b", is_block=True, calls=[CallSite(caller="b", node_id="n", link="a", kind="block")])
        tpls = templates(a, b)
        with pytest.raises(TriccParamError) as err:
            compute_effective(tpls, resolve_in(tpls))
        assert err.value.code == E_BLOCK_CYCLE


class TestUnreferenced:
    def test_declared_and_unused(self):
        page = Template(id="triage", name="triage", used=["lab"],
                        declared={"lab": spec("lab", "boolean"), "spare": spec("spare", "number")})
        page.declared = {k: v.model_copy(update={"owner": page.owner}) for k, v in page.declared.items()}
        tpls = templates(page)
        assert list(unreferenced(page, compute_effective(tpls, resolve_in(tpls))["triage"])) == ["spare"]

    def test_needed_below_counts_as_used(self):
        block = Template(id="b", name="blk", is_block=True)
        block.declared = {"site": spec("site", "string").model_copy(update={"owner": block.owner})}
        page = Template(id="p", name="page", calls=[CallSite(caller="p", node_id="n", link="b", kind="block")])
        page.declared = {"site": spec("site", "string").model_copy(update={"owner": page.owner})}
        tpls = templates(block, page)
        assert list(unreferenced(page, compute_effective(tpls, resolve_in(tpls))["p"])) == []


class TestBind:
    params = {"site": spec("site", "string", default="oral"), "lab": spec("lab", "boolean")}

    def test_call_arg_over_inherited_over_default(self):
        caller = {"site": (self.params["site"], "rectal"), "lab": (self.params["lab"], True)}
        assert bind(self.params, {"site": "axillary"}, caller, "u")["site"][1] == "axillary"
        assert bind(self.params, {}, caller, "u")["site"][1] == "rectal"
        assert bind(self.params, {}, {}, "u")["site"][1] == "oral"
        assert bind(self.params, {}, caller, "u")["lab"][1] is True

    def test_override_leaves_caller_unchanged(self):
        caller = {"site": (self.params["site"], "rectal")}
        bind(self.params, {"site": "axillary"}, caller, "u")
        assert caller["site"][1] == "rectal"

    def test_required_names_the_chain(self):
        with pytest.raises(TriccParamError) as err:
            bind({"site": spec("site", "string", required=True)}, {}, {}, "triage > block t-ax")
        assert err.value.code == E_PARAM_REQUIRED
        assert "triage > block t-ax" in str(err.value)


# ---------------------------------------------------------------------------
# Projects
# ---------------------------------------------------------------------------


def copy_fixture(tmp_path):
    root = tmp_path / "project"
    shutil.copytree(FIXTURE, root)
    return root


def edit_yaml(path, change):
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    change(data)
    path.write_text(yaml.safe_dump(data, sort_keys=False), encoding="utf-8")


def node(data, node_id):
    return next(n for n in data["nodes"] if n["id"] == node_id)


def load(root):
    config = TriccProjectConfig(**yaml.safe_load((root / "tricc.yaml").read_text(encoding="utf-8")))
    files = sorted(glob.glob(str(root / "activities" / "*.yaml"))) + sorted(glob.glob(str(root / "blocks" / "*.yaml")))
    return load_input_project(
        [("YamlStrategy", files, read_input_file_contents(files))],
        str(root / "media"), config, config.interventions[0],
    )


def survey(root):
    assert run_project_build(str(root), str(root / "out")) == 0
    xlsx = glob.glob(str(root / "out" / "**" / "*.xlsx"), recursive=True)[0]
    rows = pd.read_excel(xlsx, sheet_name="survey").fillna("")
    return {r["name"]: r for _, r in rows.iterrows()}


class TestProject:
    def test_two_uses_with_different_values(self, tmp_path):
        rows = survey(copy_fixture(tmp_path))
        assert {"temp_axillary", "temp_rectal", "fever_axillary", "fever_rectal"} <= set(rows)
        assert ">37.5" in rows["fever_axillary"]["relevance"]
        assert ">38" in rows["fever_rectal"]["relevance"]
        # the intervention's args reach the activity parameter
        assert str(rows["lab_note"]["relevance"]) == "1"

    def test_same_values_twice_is_the_same_concept(self, tmp_path):
        root = copy_fixture(tmp_path)
        edit_yaml(root / "activities" / "triage.activity.yaml",
                  lambda d: node(d, "t-re").update(args={"site": "axillary"}))
        rows = survey(root)
        versions = sorted(n for n in rows if n.startswith("temp_axillary"))
        assert len(versions) == 2
        # the later copy is not asked again once the concept is captured
        assert "=''" in rows[versions[1]]["relevance"]

    def test_name_parameter_tells_uses_apart(self, tmp_path):
        root = copy_fixture(tmp_path)

        def block(d):
            d["params"].append({"name": "prefix", "type": "name", "required": True})
            for n in d["nodes"]:
                if n.get("name", "").startswith(("temp_", "fever_")):
                    n["name"] = "{{prefix}}_" + n["name"]
                if n["type"] == "rhombus":
                    n["reference"] = '"{{prefix|raw}}_temp_{{site|raw}}" > {{threshold}}'

        def triage(d):
            node(d, "t-ax")["args"] = {"site": "axillary", "prefix": "admission"}
            node(d, "t-re")["args"] = {"site": "axillary", "prefix": "discharge"}

        edit_yaml(root / "blocks" / "measure-temperature.block.yaml", block)
        edit_yaml(root / "activities" / "triage.activity.yaml", triage)
        rows = survey(root)
        assert {"admission_temp_axillary", "discharge_temp_axillary"} <= set(rows)

    def test_missing_required_value(self, tmp_path):
        root = copy_fixture(tmp_path)
        edit_yaml(root / "activities" / "triage.activity.yaml", lambda d: node(d, "t-ax").update(args={}))
        with pytest.raises(TriccParamError) as err:
            load(root)
        assert err.value.code == E_PARAM_REQUIRED
        assert "t-ax" in str(err.value)

    def test_unknown_intervention_argument(self, tmp_path):
        root = copy_fixture(tmp_path)
        edit_yaml(root / "tricc.yaml", lambda d: d["interventions"][0]["args"].update(nope=1))
        with pytest.raises(TriccParamError) as err:
            load(root)
        assert err.value.code == E_PARAM_UNKNOWN

    def test_goto_args_build_one_activity_per_value(self, tmp_path):
        root = copy_fixture(tmp_path)
        (root / "activities" / "vitals.activity.yaml").write_text(yaml.safe_dump({
            "id": "vitals", "name": "vitals", "title": "Vitals",
            "nodes": [
                {"id": "v-s", "type": "activity_start"},
                {"id": "v-call", "type": "block", "link": "measure_temperature"},
                {"id": "v-n", "type": "note", "name": "done_{{site}}", "label": "Done {{site}}"},
                {"id": "v-e", "type": "activity_end"},
            ],
            "edges": [{"source": "v-s", "target": "v-call"}, {"source": "v-call", "target": "v-n"},
                      {"source": "v-n", "target": "v-e"}],
        }), encoding="utf-8")

        def triage(d):
            d["params"] = []
            d["nodes"] = [
                {"id": "t-s", "type": "start"},
                {"id": "t-g1", "type": "goto", "link": "vitals", "args": {"site": "axillary"}},
                {"id": "t-g2", "type": "goto", "link": "vitals", "args": {"site": "rectal"}},
                {"id": "t-e", "type": "end", "name": "the_end"},
            ]
            d["edges"] = [{"source": "t-s", "target": "t-g1"}, {"source": "t-g1", "target": "t-g2"},
                          {"source": "t-g2", "target": "t-e"}]

        edit_yaml(root / "activities" / "triage.activity.yaml", triage)
        edit_yaml(root / "tricc.yaml", lambda d: (d["interventions"][0].pop("args"),
                                                  d["interventions"][0]["activity"].append(
                                                      "activities/vitals.activity.yaml")))
        rows = survey(root)
        # vitals inherits `site` from the block it uses; each goto value is its own instance
        assert {"done_axillary", "done_rectal", "temp_axillary", "temp_rectal"} <= set(rows)

    def test_parameter_concepts(self, tmp_path):
        project = load(copy_fixture(tmp_path))
        concepts = {c.code: c for cs in project.code_systems.values() for c in cs.concept or []}
        site = concepts["param_measure_temperature_site"]
        props = [(p.code, p.valueCode or p.valueString) for p in site.property]
        assert ("kind", "parameter") in props and ("dataType", "coded") in props
        assert {("option", "axillary"), ("option", "rectal")} <= set(props)
        threshold = concepts["param_measure_temperature_threshold"]
        assert ("default", "37.5") in [(p.code, p.valueString) for p in threshold.property]

    def test_project_dictionary_wins(self, tmp_path):
        root = copy_fixture(tmp_path)
        (root / "terminology").mkdir()
        (root / "terminology" / "calc.json").write_text(
            '{"resourceType": "CodeSystem", "id": "proj-calculate", "name": "proj-calculate", "status": "draft",'
            ' "content": "complete", "url": "http://example.org/proj-calculate",'
            ' "concept": [{"code": "param_measure_temperature_site", "display": "Where measured"}]}',
            encoding="utf-8",
        )
        edit_yaml(root / "tricc.yaml", lambda d: d.update(terminology=["terminology/calc.json"]))
        config = TriccProjectConfig(**yaml.safe_load((root / "tricc.yaml").read_text(encoding="utf-8")))
        files = [
            str(root / "activities" / "triage.activity.yaml"),
            str(root / "blocks" / "measure-temperature.block.yaml"),
        ]
        text = (root / "terminology" / "calc.json").read_text(encoding="utf-8")
        project = load_input_project(
            [("YamlStrategy", files, read_input_file_contents(files))], str(root / "media"), config,
            config.interventions[0], terminology=[("calc.json", text)],
        )
        cs = project.code_systems["proj-calculate"]
        site = next(c for c in cs.concept if c.code == "param_measure_temperature_site")
        assert site.display == "Where measured" and not site.property
        # the concept it lacked goes to the same calculate dictionary
        assert any(c.code == "param_measure_temperature_threshold" for c in cs.concept)

    def test_snippet_names_still_read(self, tmp_path):
        root = copy_fixture(tmp_path)
        edit_yaml(root / "blocks" / "measure-temperature.block.yaml",
                  lambda d: node(d, "mt-s").update(type="snippet_start"))
        edit_yaml(root / "activities" / "triage.activity.yaml",
                  lambda d: [n.update(type="snippet") for n in d["nodes"] if n["type"] == "block"])
        assert {"temp_axillary", "temp_rectal"} <= set(survey(root))

    def test_blocks_are_not_start_pages(self, tmp_path):
        project = load(copy_fixture(tmp_path))
        starts = [p for v in project.start_pages.values() for p in (v if isinstance(v, list) else [v])]
        assert all(p.id not in project.blocks for p in starts)
        assert len(project.blocks) == 2


# ---------------------------------------------------------------------------
# draw.io
# ---------------------------------------------------------------------------

DRAWIO = os.path.join(os.path.dirname(__file__), "data", "drawio_blocks", "block_params.drawio")


def drawio_survey(tmp_path, text=None):
    from tricc_oo.runner import run_one_export

    text = text if text is not None else open(DRAWIO, encoding="utf-8").read()
    out = tmp_path / "out"
    run_one_export([DRAWIO], [text], str(out), "DrawioStrategy", "XLSFormStrategy", TriccProjectConfig(), None)
    xlsx = glob.glob(str(out / "**" / "*.xlsx"), recursive=True)[0]
    rows = pd.read_excel(xlsx, sheet_name="survey").fillna("")
    return {r["name"]: r for _, r in rows.iterrows()}


class TestDrawio:
    def test_same_form_as_yaml(self, tmp_path):
        rows = drawio_survey(tmp_path)
        assert {"temp_axillary", "temp_rectal", "fever_axillary", "fever_rectal", "lab_note"} <= set(rows)
        assert ">37.5" in rows["fever_axillary"]["relevance"]
        assert ">38" in rows["fever_rectal"]["relevance"]
        # declared on the page's parameters shape (boolean=true), which is not a node
        assert str(rows["lab_note"]["relevance"]) == "1"
        assert not any("Parameters" in str(r.get("label::en", "")) for r in rows.values())

    def test_page_without_parameters_is_still_built(self, tmp_path):
        from tricc_oo.strategies.input.base_input_strategy import BaseInputStrategy
        from tricc_oo.strategies.input.drawio import DrawioStrategy

        plain = (
            '  <diagram name="Plain" id="plainPage00000000001"><mxGraphModel><root>'
            '<mxCell id="0" /><mxCell id="1" parent="0" />'
            '<object odk_type="activity_start" label="Plain" name="plain" id="pl-start-00000001">'
            '<mxCell parent="1" vertex="1"><mxGeometry as="geometry" /></mxCell></object>'
            '<object odk_type="note" label="Hello" name="plain_note" id="pl-note-000000001">'
            '<mxCell parent="1" vertex="1"><mxGeometry as="geometry" /></mxCell></object>'
            '<mxCell id="pl-e1-00000000001" edge="1" parent="1" source="pl-start-00000001" '
            'target="pl-note-000000001"><mxGeometry as="geometry" /></mxCell>'
            "</root></mxGraphModel></diagram>\n"
        )
        text = open(DRAWIO, encoding="utf-8").read().replace("</mxfile>", plain + "</mxfile>")
        project = BaseInputStrategy.new_project()
        DrawioStrategy([]).load([text], str(tmp_path), project)
        page = project.pages["plainPage00000000001"]
        assert "plain_note" in {getattr(n, "name", None) for n in page.nodes.values()}
        assert "plainPage00000000001" not in project.blocks

    def test_snippet_names_still_read(self, tmp_path):
        text = open(DRAWIO, encoding="utf-8").read()
        text = text.replace('odk_type="block_start"', 'odk_type="snippet_start"')
        text = text.replace('odk_type="block"', 'odk_type="snippet"')
        assert {"temp_axillary", "temp_rectal"} <= set(drawio_survey(tmp_path, text))


class TestCalculateDictionary:
    def cs(self, id_, tagged=False):
        from fhir.resources.codesystem import CodeSystem

        from tricc_oo.converters.datadictionnary import CALCULATE_ROLE, role_meta

        extra = {"meta": role_meta(CALCULATE_ROLE)} if tagged else {}
        return CodeSystem(id=id_, name=id_, url=f"http://example.org/{id_}", status="draft", content="complete",
                          **extra)

    def test_tag_wins(self):
        from tricc_oo.strategies.input.param_build import calculate_code_system_key

        systems = {"proj-calculate": self.cs("proj-calculate"), "calc": self.cs("calc", tagged=True)}
        assert calculate_code_system_key(systems, "proj-calculate") == "calc"

    def test_configured_then_name(self):
        from tricc_oo.strategies.input.param_build import calculate_code_system_key

        systems = {"proj-calculate": self.cs("proj-calculate"), "mine": self.cs("mine")}
        assert calculate_code_system_key(systems, "http://example.org/mine") == "mine"
        assert calculate_code_system_key(systems) == "proj-calculate"
        assert calculate_code_system_key({}) == "calculate"

    def test_created_calculate_system_is_tagged(self, tmp_path):
        from tricc_oo.converters.datadictionnary import CALCULATE_ROLE, has_role

        project = load(copy_fixture(tmp_path))
        assert has_role(project.code_systems["calculate"], CALCULATE_ROLE)
