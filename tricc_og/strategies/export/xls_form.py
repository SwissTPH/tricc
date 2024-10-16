from tricc_og.builders.xls_form import (
    CHOICE_MAP,
    SURVEY_MAP,
    convert,
    or_join,
    and_join,
    negate_term,
)
from tricc_og.builders.utils import clean_name
import pandas as pd
import abc
import logging
import os
from tricc_og.visitors.tricc_project import walktrhough_tricc_processed_stached, is_ready_to_process
import datetime
from .base_export_strategy import BaseExportStrategy
from tricc_og.models.base import (
    TriccOperation,
    TriccStatic,
    TriccSCV
)
from tricc_og.models.ordered_set import OrderedSet
from tricc_og.models.operators import TriccOperator

logger = logging.getLogger("default")


class XLSFormStrategy(BaseExportStrategy):
    processes = ["main"]
    output_path = None
    project = None
    input_strategy = None
    cur_group = None

    df_survey = pd.DataFrame(columns=SURVEY_MAP.keys())
    df_calculate = pd.DataFrame(columns=SURVEY_MAP.keys())
    df_choice = pd.DataFrame(columns=CHOICE_MAP.keys())

    def __init__(self, project, output_path, in_strategy):
        self.output_path = output_path
        self.project = project
        self.input_strategy = in_strategy

    def export_as_xlsx(self, graph, df_survey, df_choice, df_settings, newpath):
        #for node in self.project.impl_graph.nodes:
            #latest_instance = graph.nodes[node]['data'].instances[-1]

            #nodes_dict['name'].append(latest_instance.instantiate.code)
            #nodes_dict['label'].append(latest_instance.instantiate.label)
            #nodes_dict['type'].append(latest_instance.instantiate.type_scv.code)

        # df_survey.loc[:,'name'] = nodes_dict['name']
        # df_survey.loc[:,'label'] = nodes_dict['label']
        # df_survey.loc[:,'type'] = nodes_dict['type']
        #df_survey = df_survey.assign(**{k: nodes_dict[k] for k in ['name', 'label', 'type']})

        # self.df_survey.merge(nodes_dict[['name','label']], how='left', on= 'name')
        with pd.ExcelWriter(newpath, engine="xlsxwriter") as writer:
            #if len(df_survey[df_survey['name'] == 'version']):
            #    df_survey.loc[df_survey['name'] == 'version', 'label'] = f"v{version}"
            df_survey.to_excel(writer, sheet_name="survey", index=False)
            df_choice.to_excel(writer, sheet_name="choices", index=False)
            df_settings.to_excel(writer, sheet_name="settings", index=False)
        return 

    def execute(self, processes=[]):
        stashed_nodes = OrderedSet()
        processed_nodes = OrderedSet()

        calculates = []
        # context need to have their own rules/calculate
        # all QS context will take the apply the upstream context
        # therefore the parser need to know current contextes AND between level and
        # OR for concurrent contextes
        # all the node with only 1 context in the in_edge should be grouped together

        # 1 creating the calculates for the contexts

        if "main" in self.project.impl_graph_process_start:
            main_start = self.project.impl_graph_process_start["main"][0].scv()
        else:
            logger.error("form id required in the first start node")
            exit()
        title = self.project.title
        form_id = self.project.scv()
        file_name = form_id + ".xlsx"
        # make a 'settings' tab
        nodes_dict = {key: [] for key in ['name', 'label', 'type', 'calculation']}
        now = datetime.datetime.now()
        indx = [[1]]

        settings = {
            "form_title": title,
            "form_id": form_id,
            "version": now,
            "default_language": "English (en)",
            "style": "pages",
        }
        df_settings = pd.DataFrame(settings, index=indx)

        newpath = os.path.join(self.output_path, file_name)
        # create newpath if it not exists
        if not os.path.exists(self.output_path):
            os.makedirs(self.output_path)

        walktrhough_tricc_processed_stached(
            self.project.impl_graph,
            main_start,
            convert,
            processed_nodes,
            stashed_nodes,
            strategy=self,
            node_path=[],
            df_survey=self.df_survey,
            df_choices=self.df_choice,
        )
        logger.info("dangling nodes")
        for node in self.project.impl_graph.nodes():
            if node not in processed_nodes:
                logger.info(node)
        # create a Pandas Excel writer using XlsxWriter as the engine
        self.export_as_xlsx(self.project.impl_graph, self.df_survey, self.df_choice, df_settings, newpath)

    def get_tricc_operation_expression(self, operation):
        ref_expressions = []
        for r in operation.reference:
            r_expr = self.get_tricc_operation_operand(r)
            if isinstance(r_expr, str):
                r_expr = safe_to_bool_logic(r_expr)
            ref_expressions.append(r_expr)
        # build lower level
        if hasattr(self, f"tricc_operation_{operation.operator}"):
            callable = getattr(self, f"tricc_operation_{operation.operator}")
            return callable(ref_expressions)
        else:
            raise NotImplementedError(
                f"This type of opreation '{operation.operator}' is not supported in this strategy"
            )

    def tricc_operation_not(self, ref_expressions):
        return negate_term(ref_expressions[0])

    def tricc_operation_and(self, ref_expressions):
        return and_join(ref_expressions)

    def tricc_operation_or(self, ref_expressions):
        return or_join(ref_expressions)

    def tricc_operation_or_and(self, ref_expressions):
        return and_join([ref_expressions[0], or_join(ref_expressions[1:])])

    def tricc_operation_native(self, ref_expressions):
        return ref_expressions

    def tricc_operation_istrue(self, ref_expressions):
        return f"${{{ref_expressions[0]}}} > 0"

    def tricc_operation_isfalse(self, ref_expressions):
        return f"${{{ref_expressions[0]}}} = 0"

    def tricc_operation_selected(self, ref_expressions):
        parts = []
        for s in ref_expressions[1:]:
            parts.append(f"selected(${{{ref_expressions[0]}}}, {s})")
        return self.tricc_operation_or(parts)

    def tricc_operation_more_or_equal(self, ref_expressions):
        return f"${{{ref_expressions[0]}}} >= {ref_expressions[1]}"

    def tricc_operation_less_or_equal(self, ref_expressions):
        return f"${{{ref_expressions[0]}}} <= {ref_expressions[1]}"

    def tricc_operation_more(self, ref_expressions):
        return f"${{{ref_expressions[0]}}} > {ref_expressions[1]}"

    def tricc_operation_less(self, ref_expressions):
        return f"${{{ref_expressions[0]}}} < {ref_expressions[1]}"

    def tricc_operation_between(self, ref_expressions):
        return f"${{{ref_expressions[0]}}} >= {ref_expressions[1]} and ${{{ref_expressions[0]}}} < {ref_expressions[2]}"

    def tricc_operation_equal(self, ref_expressions):
        return f"${{{ref_expressions[0]}}} = {ref_expressions[1]}"

    def tricc_operation_not_equal(self, ref_expressions):
        return f"${{{ref_expressions[0]}}} != {ref_expressions[1]}"

    def tricc_operation_case(self, ref_expressions):
        ifs = 0
        parts = []
        for i in range(int(len(ref_expressions) / 2)):
            if i * 2 + 1 <= len(ref_expressions):
                parts.append(f"if({ref_expressions[i*2]},{ref_expressions[i*2+1]}")
                ifs += 1
            else:
                parts.append(ref_expressions[i * 2])
        # join the if
        exp = ",".join(parts)
        # in case there is no default put ''
        if len(ref_expressions) % 2 == 0:
            exp += ",''"
        # add the closing )
        for i in range(ifs):
            exp += ")"
        return exp

    def tricc_operation_if(self, ref_expressions):
        return self.tricc_operation_case(ref_expressions)

    def tricc_operation_contains(self, ref_expressions):
        return f"contains(${{{ref_expressions[0]}}}, {ref_expressions[1]})"

    def tricc_operation_exists(self, ref_expressions):
        parts = []
        for ref in ref_expressions:
            parts.append(self.tricc_operation_not_equal([ref, "''"]))
        return self.tricc_operation_and(parts)

    # function transform an object to XLSFORM value
    # @param r reference to be translated
    def get_tricc_operation_operand(self, r):
        if isinstance(r, TriccOperation):
            return self.get_tricc_operation_expression(r)
        elif isinstance(r, TriccStatic):
            return f"'{r.value}'"
        elif isinstance(r, str):
            return f"'{r}'"
        elif isinstance(r, (int, float)):
            return r
        elif isinstance(r, TriccSCV):
            return clean_name(r.value)
        else:
            raise NotImplementedError(
                f"This type of node {r.__class__} is not supported within an operation"
            )

    OPERATOR_EXPORT = {
        TriccOperator.EQUAL: tricc_operation_equal,
        TriccOperator.AND: tricc_operation_and,
        TriccOperator.ADD_OR: tricc_operation_or_and,
        TriccOperator.NOT: tricc_operation_not,
        TriccOperator.OR: tricc_operation_or,
        TriccOperator.NOT_EQUAL: tricc_operation_not_equal,
        TriccOperator.LESS_OR_EQUAL: tricc_operation_less_or_equal,
        TriccOperator.MORE_OR_EQUAL: tricc_operation_more_or_equal,
        TriccOperator.BETWEEN: tricc_operation_between,
        TriccOperator.NATIVE: tricc_operation_native,
        TriccOperator.IF: tricc_operation_if,
        TriccOperator.IFS: tricc_operation_if,
        TriccOperator.ISFALSE: tricc_operation_isfalse,
        TriccOperator.ISTRUE: tricc_operation_istrue,
        TriccOperator.EXISTS: tricc_operation_exists,
        TriccOperator.CONTAINS: tricc_operation_contains,
        TriccOperator.LESS: tricc_operation_less,
        TriccOperator.MORE: tricc_operation_more,
    }  