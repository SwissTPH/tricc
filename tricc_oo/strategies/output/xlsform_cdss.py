import logging
from tricc_oo.models.tricc import TriccNodeActivity
from tricc_oo.models.calculate import TriccNodeInput, TriccNodePopulate
import re
from typing import List

from tricc_oo.models.tricc import TriccNodeActivity
from tricc_oo.models.calculate import TriccNodeInput
from tricc_oo.models.base import (
    TriccOperation,
    TriccOperator,
    TriccReference,
    TriccStatic,
)
from tricc_oo.converters.tricc_to_xls_form import get_export_name
from tricc_oo.strategies.output.xls_form import XLSFormStrategy
from tricc_oo.strategies.registry import register_output_strategy
from tricc_oo.models.lang import SingletonLangClass

langs = SingletonLangClass()
logger = logging.getLogger("default")

_TRIGGER_REF_SPLIT = re.compile(r"\s*,\s*|\s+")


def _comma_join_survey_trigger_refs(*chunks: str) -> str:
    """ODK/pyxform require comma-separated ``${field}`` tokens in the survey trigger column."""
    parts: List[str] = []
    for ch in chunks:
        if not ch:
            continue
        s = str(ch).strip()
        if not s:
            continue
        for p in _TRIGGER_REF_SPLIT.split(s):
            p = p.strip()
            if p and p not in parts:
                parts.append(p)
    return ", ".join(parts)


@register_output_strategy("XLSFormCDSSStrategy")
class XLSFormCDSSStrategy(XLSFormStrategy):

    def process_export(self, start_pages, **kwargs):
        self.activity_export(start_pages[self.processes[0]], **kwargs)
        # self.add_tab_breaks_choice()
        # self.add_wfx_choice()

    def generate_export(self, node, **kwargs):
        # Coalesce($this, …) becomes coalesce(${…},'') plus triggers (CDSS only).
        self._extract_this_coalesce_trigger(node)
        return super().generate_export(node, **kwargs)

    @staticmethod
    def _is_this_marker(value):
        if isinstance(value, str):
            return value == "$this"
        if isinstance(value, (TriccStatic, TriccReference)):
            return getattr(value, "value", None) == "$this"
        return False
    def _coalesce_operand_is_this(self, value):
        """True for ``$this`` markers, including legacy ``\"\"`` from string operands."""
        if self._is_this_marker(value):
            return True
        return isinstance(value, str) and value == ""

    def _extract_this_coalesce_trigger(self, node):
        """When ``node.expression`` contains ``$this`` inside ``coalesce``, drop
        ``$this``, set ``trigger`` to every remaining field reference (same refs
        that stay in the calculation), and simplify the expression before XPath.

        Only ``node.expression`` is considered (not ``expression_reference``),
        so hidden save calculates without ``$this`` are unchanged.
        """

        def _clean_this_in_coalesce(expression):
            if not isinstance(expression, TriccOperation):
                return expression
            if expression.operator != TriccOperator.COALESCE:
                return expression
            refs = list(expression.reference)
            if any(self._coalesce_operand_is_this(r) for r in refs):
                if len(refs) == 2:
                    return [r for r in refs if not self._coalesce_operand_is_this(r)][0]
                expression.reference = [r for r in refs if not self._coalesce_operand_is_this(r)]
                return expression

            expression.reference = [_clean_this_in_coalesce(ref) for ref in refs]
            return expression

        expression = getattr(node, "expression", None)
        if not isinstance(expression, TriccOperation) or expression.operator != TriccOperator.COALESCE:
            return
        if not any(self._coalesce_operand_is_this(r) for r in expression.reference):
            return

        node.expression = _clean_this_in_coalesce(expression)
        cleaned = node.expression
        if isinstance(cleaned, TriccOperation):
            trigger_refs = cleaned.get_references()
        else:
            trigger_refs = [cleaned]

        trigger_tokens = []
        for ref in trigger_refs:
            if self._coalesce_operand_is_this(ref):
                continue
            name = ref.value if isinstance(ref, TriccReference) else get_export_name(ref)
            token = f"${{{name}}}"
            if token not in trigger_tokens:
                trigger_tokens.append(token)

        if not trigger_tokens:
            return
        new_trigger = ", ".join(trigger_tokens)
        existing = getattr(node, "trigger", None)
        if existing:
            if isinstance(existing, (TriccOperation, TriccStatic, TriccReference)):
                existing_str = self.get_tricc_operation_expression(existing)
            else:
                existing_str = str(existing)
            node.trigger = _comma_join_survey_trigger_refs(existing_str, new_trigger)
        else:
            node.trigger = new_trigger

    def export_inputs(self, activity, inputs=[], **kwargs):
        for node in activity.nodes.values():
            if isinstance(node, TriccNodeActivity):
                inputs = self.export_inputs(node, inputs, **kwargs)
            if isinstance(node, (TriccNodeInput, TriccNodePopulate)):
                inputs.append(node)
        return inputs
   
    def tricc_operation_has_qualifier(self, ref_expressions):
        raise NotImplementedError("This type of opreration  is not supported in this strategy")

    def tricc_operation_age_day(self, ref_expressions):
        dob_node_name = ref_expressions[0].value if ref_expressions else "birthday"
        return f"int((today()-date(${{{dob_node_name}}})))"

    def tricc_operation_age_month(self, ref_expressions):
        dob_node_name = ref_expressions[0].value if ref_expressions else "birthday"
        return f"int((today()-date(${{{dob_node_name}}})) div 30.25)"

    def tricc_operation_age_year(self, ref_expressions):
        dob_node_name = ref_expressions[0].value if ref_expressions else "birthday"
        return f"int((today()-date(${{{dob_node_name}}})) div 365.25)"

    def add_wfx_choice(self):
        empty = langs.get_trads("", force_dict=True)
        new_rows = [
            [
                "wfl",
                "y45_0",
                *list(empty.values()),
                *list(empty.values()),
                "f",
                0,
                110,
                -0.3833,
                0.09029,
                2.4607,
            ],
            [
                "wfa",
                "y45_1",
                *list(empty.values()),
                *list(empty.values()),
                "f",
                0,
                18500,
                -0.3833,
                0.0903,
                2.4777,
            ],
            [
                "wfh",
                "y45_2",
                *list(empty.values()),
                *list(empty.values()),
                "f",
                0,
                125,
                -0.3833,
                0.0903,
                2.4947,
            ],
        ]

        for row in new_rows:
            self.df_choice.loc[len(self.df_choice)] = row

        label = langs.get_trads("hidden", force_dict=True)
        empty = langs.get_trads("", force_dict=True)
        self.df_survey.loc[len(self.df_survey)] = [
            "select_one wfl",
            "wfl",
            *list(label.values()),
            *list(empty.values()),  # hint
            *list(empty.values()),  # help
            "",  # default
            "",  # 'appearance', clean_name
            "",  # 'constraint',
            *list(empty.values()),  # 'constraint_message'
            "0",  # 'relevance'
            "",  # 'disabled'
            "1",  # 'required'
            *list(empty.values()),  # 'required message'
            "",  # 'read only'
            "",  # 'expression'
            "",
            "",  # 'repeat_count'
            "",  # 'image'
            "",
        ]
        self.df_survey.loc[len(self.df_survey)] = [
            "select_one wfa",
            "wfa",
            *list(label.values()),
            *list(empty.values()),  # hint
            *list(empty.values()),  # help
            "",  # default
            "",  # 'appearance', clean_name
            "",  # 'constraint',
            *list(empty.values()),  # 'constraint_message'
            "0",  # 'relevance'
            "",  # 'disabled'
            "1",  # 'required'
            *list(empty.values()),  # 'required message'
            "",  # 'read only'
            "",  # 'expression'
            "",
            "",  # 'repeat_count'
            "",  # 'image'
            "",
        ]
        self.df_survey.loc[len(self.df_survey)] = [
            "select_one wfh",
            "wfh",
            *list(label.values()),
            *list(empty.values()),  # hint
            *list(empty.values()),  # help
            "",  # default
            "",  # 'appearance', clean_name
            "",  # 'constraint',
            *list(empty.values()),  # 'constraint_message'
            "0",  # 'relevance'
            "",  # 'disabled'
            "1",  # 'required'
            *list(empty.values()),  # 'required message'
            "",  # 'read only'
            "",  # 'expression'
            "",
            "",  # 'repeat_count'
            "",  # 'image'
            "",
        ]

    def add_tab_breaks_choice(self):
        label = langs.get_trads("hidden", force_dict=True)
        empty = langs.get_trads("", force_dict=True)
        self.df_survey.loc[len(self.df_survey)] = [
            "select_one tab-label-4",
            "tab_label_4",
            *list(label.values()),
            *list(empty.values()),  # hint
            *list(empty.values()),  # help
            "",  # default
            "",  # 'appearance', clean_name
            "",  # 'constraint',
            *list(empty.values()),  # 'constraint_message'
            "0",  # 'relevance'
            "",  # 'disabled'
            "1",  # 'required'
            *list(empty.values()),  # 'required message'
            "",  # 'read only'
            "",
            "",  # 'expression'
            "",  # 'repeat_count'
            "",  # 'image'
            "",
        ]
        new_rows = [
            [
                "tab-label-4",
                0,
                langs.get_trads("--"),
                *list(empty.values()),
                "",
                "",
                "",
                "",
                "",
                "",
            ],
            [
                "tab-label-4",
                1,
                langs.get_trads("--"),
                *list(empty.values()),
                "",
                "",
                "",
                "",
                "",
                "",
            ],
            [
                "tab-label-4",
                2,
                langs.get_trads("1/2"),
                *list(empty.values()),
                "",
                "",
                "",
                "",
                "",
                "",
            ],
            [
                "tab-label-4",
                3,
                langs.get_trads("1/2"),
                *list(empty.values()),
                "",
                "",
                "",
                "",
                "",
                "",
            ],
            [
                "tab-label-4",
                4,
                langs.get_trads("1"),
                *list(empty.values()),
                "",
                "",
                "",
                "",
                "",
                "",
            ],
            [
                "tab-label-4",
                5,
                langs.get_trads("1"),
                *list(empty.values()),
                "",
                "",
                "",
                "",
                "",
                "",
            ],
            [
                "tab-label-4",
                6,
                langs.get_trads("1 and 1/2"),
                *list(empty.values()),
                "",
                "",
                "",
                "",
                "",
                "",
            ],
            [
                "tab-label-4",
                7,
                langs.get_trads("1 and 1/2"),
                *list(empty.values()),
                "",
                "",
                "",
                "",
                "",
                "",
            ],
            [
                "tab-label-4",
                8,
                langs.get_trads("2"),
                *list(empty.values()),
                "",
                "",
                "",
                "",
                "",
                "",
            ],
            [
                "tab-label-4",
                9,
                langs.get_trads("2"),
                *list(empty.values()),
                "",
                "",
                "",
                "",
                "",
                "",
            ],
            [
                "tab-label-4",
                10,
                langs.get_trads("2 and 1/2"),
                *list(empty.values()),
                "",
                "",
                "",
                "",
                "",
                "",
            ],
            [
                "tab-label-4",
                11,
                langs.get_trads("2 and 1/2"),
                *list(empty.values()),
                "",
                "",
                "",
                "",
                "",
                "",
            ],
            [
                "tab-label-4",
                12,
                langs.get_trads("3"),
                *list(empty.values()),
                "",
                "",
                "",
                "",
                "",
                "",
            ],
            [
                "tab-label-4",
                13,
                langs.get_trads("3"),
                *list(empty.values()),
                "",
                "",
                "",
                "",
                "",
                "",
            ],
            [
                "tab-label-4",
                14,
                langs.get_trads("3 and 1/2"),
                *list(empty.values()),
                "",
                "",
                "",
                "",
                "",
                "",
            ],
            [
                "tab-label-4",
                15,
                langs.get_trads("3 and 1/2"),
                *list(empty.values()),
                "",
                "",
                "",
                "",
                "",
                "",
            ],
            [
                "tab-label-4",
                16,
                langs.get_trads("4"),
                *list(empty.values()),
                "",
                "",
                "",
                "",
                "",
                "",
            ],
            [
                "tab-label-4",
                17,
                langs.get_trads("4"),
                *list(empty.values()),
                "",
                "",
                "",
                "",
                "",
                "",
            ],
            [
                "tab-label-4",
                18,
                langs.get_trads("4 and 1/2"),
                *list(empty.values()),
                "",
                "",
                "",
                "",
                "",
                "",
            ],
            [
                "tab-label-4",
                19,
                langs.get_trads("4 and 1/2"),
                *list(empty.values()),
                "",
                "",
                "",
                "",
                "",
                "",
            ],
            [
                "tab-label-4",
                20,
                langs.get_trads("5"),
                *list(empty.values()),
                "",
                "",
                "",
                "",
                "",
                "",
            ],
            [
                "tab-label-4",
                21,
                langs.get_trads("5"),
                *list(empty.values()),
                "",
                "",
                "",
                "",
                "",
                "",
            ],
            [
                "tab-label-4",
                22,
                langs.get_trads("5 and 1/2"),
                *list(empty.values()),
                "",
                "",
                "",
                "",
                "",
                "",
            ],
            [
                "tab-label-4",
                23,
                langs.get_trads("5 and 1/2"),
                *list(empty.values()),
                "",
                "",
                "",
                "",
                "",
                "",
            ],
            [
                "tab-label-4",
                24,
                langs.get_trads("6"),
                *list(empty.values()),
                "",
                "",
                "",
                "",
                "",
                "",
            ],
            [
                "tab-label-4",
                25,
                langs.get_trads("6"),
                *list(empty.values()),
                "",
                "",
                "",
                "",
                "",
                "",
            ],
            [
                "tab-label-4",
                26,
                langs.get_trads("6 and 1/2"),
                *list(empty.values()),
                "",
                "",
                "",
                "",
                "",
                "",
            ],
            [
                "tab-label-4",
                27,
                langs.get_trads("6 and 1/2"),
                *list(empty.values()),
                "",
                "",
                "",
                "",
                "",
                "",
            ],
            [
                "tab-label-4",
                28,
                langs.get_trads("7"),
                *list(empty.values()),
                "",
                "",
                "",
                "",
                "",
                "",
            ],
            [
                "tab-label-4",
                29,
                langs.get_trads("7"),
                *list(empty.values()),
                "",
                "",
                "",
                "",
                "",
                "",
            ],
            [
                "tab-label-4",
                30,
                langs.get_trads("7 and 1/2"),
                *list(empty.values()),
                "",
                "",
                "",
                "",
                "",
                "",
            ],
            [
                "tab-label-4",
                31,
                langs.get_trads("7 and 1/2"),
                *list(empty.values()),
                "",
                "",
                "",
                "",
                "",
                "",
            ],
            [
                "tab-label-4",
                32,
                langs.get_trads("8"),
                *list(empty.values()),
                "",
                "",
                "",
                "",
                "",
                "",
            ],
            [
                "tab-label-4",
                33,
                langs.get_trads("8"),
                *list(empty.values()),
                "",
                "",
                "",
                "",
                "",
                "",
            ],
            [
                "tab-label-4",
                34,
                langs.get_trads("8 and 1/2"),
                *list(empty.values()),
                "",
                "",
                "",
                "",
                "",
                "",
            ],
            [
                "tab-label-4",
                35,
                langs.get_trads("8 and 1/2"),
                *list(empty.values()),
                "",
                "",
                "",
                "",
                "",
                "",
            ],
            [
                "tab-label-4",
                36,
                langs.get_trads("9"),
                *list(empty.values()),
                "",
                "",
                "",
                "",
                "",
                "",
            ],
            [
                "tab-label-4",
                37,
                langs.get_trads("9"),
                *list(empty.values()),
                "",
                "",
                "",
                "",
                "",
                "",
            ],
            [
                "tab-label-4",
                38,
                langs.get_trads("9 and 1/2"),
                *list(empty.values()),
                "",
                "",
                "",
                "",
                "",
                "",
            ],
            [
                "tab-label-4",
                39,
                langs.get_trads("9 and 1/2"),
                *list(empty.values()),
                "",
                "",
                "",
                "",
                "",
                "",
            ],
            [
                "tab-label-4",
                40,
                langs.get_trads("10"),
                *list(empty.values()),
                "",
                "",
                "",
                "",
                "",
                "",
            ],
        ]
        for row in new_rows:
            self.df_choice.loc[len(self.df_choice)] = row
