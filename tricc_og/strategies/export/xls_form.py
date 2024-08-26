import abc
import logging
from tricc_oo.visitors.tricc import stashed_node_func
import datetime
from .base_export_strategy import BaseExportStrategy

from tricc_og.models.ordered_set import OrderedSet

logger = logging.getLogger("default")
import pandas as pd

from tricc_ogserializers.xls_form import (
    CHOICE_MAP,
    SURVEY_MAP,
    end_group,
    generate_xls_form_export,
    start_group,
)


class XLSFormStrategy(BaseExportStrategy):
    processes = ["main"]
    output_path = None
    project = None
    
    df_survey = pd.DataFrame(columns=SURVEY_MAP.keys())
    df_calculate = pd.DataFrame(columns=SURVEY_MAP.keys())
    df_choice = pd.DataFrame(columns=CHOICE_MAP.keys())


    def __init__(self, project, output_path):
        self.output_path = output_path
        self.project = project

    def execute(self, processes=[]):
        stashed_nodes = OrderedSet()
        processed_nodes = OrderedSet()
        calculates = []
        cur_group = None
        # context need to have their own rules/calculate
        # all QS context will take the apply the upstream context
        # therefore the parser need to know current contextes AND between level and
        # OR for concurrent contextes
        # all the node with only 1 context in the in_edge should be grouped together

        # 1 creating the calculates for the contexts

        if "main" in self.project.impl_graph_process_start:
            main_start = self.project.impl_graph_process_start["main"][0]
        else:
            logger.error("form id required in the first start node")
            exit()
        title = start_pages["main"].root.label
        file_name = form_id + ".xlsx"
        # make a 'settings' tab
        now = datetime.datetime.now()
        indx = [[1]]

        settings = {
            "form_title": title,
            "form_id": form_id,
            "version": version,
            "default_language": "English (en)",
            "style": "pages",
        }
        df_settings = pd.DataFrame(settings, index=indx)
        df_settings.head()

        newpath = os.path.join(self.output_path, file_name)
        # create newpath if it not exists
        if not os.path.exists(self.output_path):
            os.makedirs(self.output_path)

        walktrhough_tricc_processed_stached(
            self.project.impl_graph,
            main_start.scv(),
            export_ndoes,
            processed_nodes,
            stashed_nodes,
            self.df_survey,
            self.df_choice,
            self.df_calculate,
            self.cur_group,
        )



        # create a Pandas Excel writer using XlsxWriter as the engine
        writer = pd.ExcelWriter(newpath, engine="xlsxwriter")
        if len(self.df_survey[self.df_survey['name'] == 'version'] ):
            self.df_survey.loc[ self.df_survey['name'] == 'version', 'label'] = f"v{version}"
        self.df_survey.to_excel(writer, sheet_name="survey", index=False)
        self.df_choice.to_excel(writer, sheet_name="choices", index=False)
        df_settings.to_excel(writer, sheet_name="settings", index=False)
        
        



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
        return r

    def tricc_operation_istrue(self, ref_expressions):
        return f"{ref_expressions[0]} > 0"

    def tricc_operation_isfalse(self, ref_expressions):
        return f"{ref_expressions[0]} = 0"

    def tricc_operation_selected(self, ref_expressions):
        parts = []
        for s in ref_expressions[1:]:
            parts.append(f"selected({ref_expressions[0]}, r)")
        return self.tricc_operation_or(parts)

    def tricc_operation_more_or_equal(self, ref_expressions):
        return f"{ref_expressions[0]} >= {ref_expressions[1]}"

    def tricc_operation_less_or_equal(self, ref_expressions):
        return f"{ref_expressions[0]} <= {ref_expressions[1]}"

    def tricc_operation_more(self, ref_expressions):
        return f"{ref_expressions[0]} > {ref_expressions[1]}"

    def tricc_operation_less(self, ref_expressions):
        return f"{ref_expressions[0]} < {ref_expressions[1]}"

    def tricc_operation_between(self, ref_expressions):
        return f"{ref_expressions[0]} >= {ref_expressions[1]} and {ref_expressions[0]} < {ref_expressions[2]}"

    def tricc_operation_equal(self, ref_expressions):
        return f"{ref_expressions[0]} = {ref_expressions[1]}"

    def tricc_operation_not_equal(self, ref_expressions):
        return f"{ref_expressions[0]} != {ref_expressions[1]}"

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
        return f"contains({ref_expressions[0]}, {ref_expressions[1]})"

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
        elif isinstance(r, TriccNodeSelectOption):
            return r.name
        elif issubclass(r.__class__, TriccNodeBaseModel):
            return f"${{{get_export_name(r)}}}"
        else:
            raise NotImplementedError(
                f"This type of node {r.__class__} is not supported within an operation"
            )
