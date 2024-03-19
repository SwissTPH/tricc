"""
Strategy to build the skyp logic following the XLSForm way

"""

import datetime
import logging
import os

import pandas as pd

from tricc_oo.converters.tricc_to_xls_form import *

from tricc_oo.models import (
    TriccNodeActivity,
    TriccGroup,
)

from tricc_oo.visitors.tricc import (
    check_stashed_loop,
    walktrhough_tricc_node_processed_stached,
    is_ready_to_process,
)
from tricc_oo.serializers.xls_form import (
    CHOICE_MAP,
    SURVEY_MAP,
    end_group,
    generate_xls_form_export,
    start_group,
)
from tricc_oo.strategies.output.base_output_strategy import BaseOutPutStrategy

logger = logging.getLogger("default")

"""
    The XLSForm strategy is a strategy that will generate the XLSForm logic
    The XLSForm logic is a logic that is based on the XLSForm format
    The XLSForm format is a format that is used by the ODK Collect application
    The ODK Collect application is an application that is used to collect data on mobile devices

    document below function

    generate_xls_form_condition
    generate_xls_form_relevance
    generate_xls_form_calculate
    generate_xls_form_export
    start_group
    end_group
    walktrhough_tricc_node_processed_stached
    check_stashed_loop
    generate_xls_form_export
    generate_xls_form_export
    
"""


class XLSFormStrategy(BaseOutPutStrategy):
    df_survey = pd.DataFrame(columns=SURVEY_MAP.keys())
    df_calculate = pd.DataFrame(columns=SURVEY_MAP.keys())
    df_choice = pd.DataFrame(columns=CHOICE_MAP.keys())

    # add save nodes and merge nodes

    def generate_base(self, node, **kwargs):
        return self.generate_xls_form_condition(node, **kwargs) 

    def generate_relevance(self, node, **kwargs):
        return self.generate_xls_form_relevance(node, **kwargs)

    def generate_calculate(self, node, **kwargs):
        return self.generate_xls_form_calculate(node, **kwargs)

    def __init__(self, output_path):
        super().__init__(output_path)
        self.do_clean()

    def do_clean(self, **kwargs):
        self.calculates = {}
        self.used_calculates = {}

    def get_kwargs(self):
        return {
            "df_survey": self.df_survey,
            "df_choice": self.df_choice,
            "df_calculate": self.df_calculate,
        }

    def generate_export(self, node, **kwargs):
        return generate_xls_form_export(node, **kwargs)

    def export(self, start_pages, version):
        if start_pages["main"].root.form_id is not None:
            form_id = str(start_pages["main"].root.form_id)
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

        # create a Pandas Excel writer using XlsxWriter as the engine
        writer = pd.ExcelWriter(newpath, engine="xlsxwriter")
        if len(self.df_survey[self.df_survey['name'] == 'version'] ):
            self.df_survey.loc[ self.df_survey['name'] == 'version', 'label'] = f"v{version}"
        self.df_survey.to_excel(writer, sheet_name="survey", index=False)
        self.df_choice.to_excel(writer, sheet_name="choices", index=False)
        df_settings.to_excel(writer, sheet_name="settings", index=False)

        # close the Pandas Excel writer and output the Excel file
        # writer.save()

        # run this on a windows python instance because if not then the generated xlsx file remains open
        writer.close()
        # writer.handles = None

    def process_export(self, start_pages, **kwargs):
        self.activity_export(start_pages["main"], **kwargs)

    def activity_export(self, activity, processed_nodes=[], **kwargs):
        stashed_nodes = []
        # The stashed node are all the node that have all their prevnode processed but not from the same group
        # This logic works only because the prev node are ordered by group/parent ..
        skip_header = 0
        groups = {}
        cur_group = activity
        groups[activity.id] = 0
        path_len = 0
        # keep the vesrions on the group id, max version
        start_group(cur_group=cur_group, groups=groups, **self.get_kwargs())
        walktrhough_tricc_node_processed_stached(
            activity.root,
            self.generate_export,
            processed_nodes,
            stashed_nodes,
            path_len,
            cur_group=activity.root.group,
            **self.get_kwargs()
        )
        end_group(cur_group=activity, groups=groups, **self.get_kwargs())
        # we save the survey data frame
        df_survey_final = pd.DataFrame(columns=SURVEY_MAP.keys())
        if len(self.df_survey) > (2 + skip_header):
            df_survey_final = self.df_survey
        ## MANAGE STASHED NODES
        prev_stashed_nodes = stashed_nodes.copy()
        loop_count = 0
        len_prev_processed_nodes = 0
        while len(stashed_nodes) > 0:
            self.df_survey = pd.DataFrame(columns=SURVEY_MAP.keys())
            loop_count = check_stashed_loop(
                stashed_nodes,
                prev_stashed_nodes,
                processed_nodes,
                len_prev_processed_nodes,
                loop_count,
            )
            prev_stashed_nodes = stashed_nodes.copy()
            len_prev_processed_nodes = len(processed_nodes)
            if len(stashed_nodes) > 0:
                s_node = stashed_nodes.pop()
                # while len(stashed_nodes)>0 and isinstance(s_node,TriccGroup):
                #    s_node = stashed_nodes.pop()
                if len(s_node.prev_nodes) > 0:
                    path_len = (
                        sorted(
                            s_node.prev_nodes,
                            key=lambda p_node: p_node.path_len,
                            reverse=True,
                        )[0].path_len
                        + 1
                    )
                if s_node.group is None:
                    logger.error(
                        "ERROR group is none for node {}".format(s_node.get_name())
                    )
                start_group(
                    cur_group=s_node.group,
                    groups=groups,
                    relevance=True,
                    **self.get_kwargs()
                )
                # arrange empty group
                walktrhough_tricc_node_processed_stached(
                    s_node,
                    self.generate_export,
                    processed_nodes,
                    stashed_nodes,
                    path_len,
                    groups=groups,
                    cur_group=s_node.group,
                    **self.get_kwargs()
                )
                # add end group if new node where added OR if the previous end group was removed
                end_group(cur_group=s_node.group, groups=groups, **self.get_kwargs())
                # if two line then empty grou
                if len(self.df_survey) > (2 + skip_header):
                    if cur_group == s_node.group:
                        # drop the end group (to merge)
                        logger.debug(
                            "printing same group {}::{}::{}::{}".format(
                                s_node.group.__class__,
                                s_node.group.get_name(),
                                s_node.id,
                                s_node.group.instance,
                            )
                        )
                        df_survey_final.drop(
                            index=df_survey_final.index[-1], axis=0, inplace=True
                        )
                        self.df_survey = self.df_survey[(1 + skip_header) :]
                        df_survey_final = pd.concat(
                            [df_survey_final, self.df_survey], ignore_index=True
                        )

                    else:
                        logger.debug(
                            "printing group {}::{}::{}::{}".format(
                                s_node.group.__class__,
                                s_node.group.get_name(),
                                s_node.id,
                                s_node.group.instance,
                            )
                        )
                        df_survey_final = pd.concat(
                            [df_survey_final, self.df_survey], ignore_index=True
                        )
                    cur_group = s_node.group

        # add the calulate

        self.df_calculate = self.df_calculate.dropna(axis=0, subset=["calculation"])
        df_empty_calc = self.df_calculate[self.df_calculate["calculation"] == ""]
        self.df_calculate = self.df_calculate.drop(df_empty_calc.index)
        self.df_survey = pd.concat(
            [df_survey_final, self.df_calculate], ignore_index=True
        )
        df_duplicate = self.df_calculate[
            self.df_calculate.duplicated(subset=["calculation"], keep="first")
        ]
        # self.df_survey=self.df_survey.drop_duplicates(subset=['name'])
        for index, drop_calc in df_duplicate.iterrows():
            # remove the duplicate
            replace_name = False
            # find the actual calcualte
            similar_calc = self.df_survey[
                (drop_calc["calculation"] == self.df_survey["calculation"])
                & (self.df_survey["type"] == "calculate")
            ]
            same_calc = self.df_survey[self.df_survey["name"] == drop_calc["name"]]
            if len(same_calc) > 1:
                # check if all calc have the same name
                if len(same_calc) == len(similar_calc):
                    # drop all but one
                    self.df_survey.drop(same_calc.index[1:])
                elif len(same_calc) < len(similar_calc):
                    self.df_survey.drop(same_calc.index)
                    replace_name = True
            elif len(same_calc) == 1:
                self.df_survey.drop(similar_calc.index)
                replace_name = True

            if replace_name:
                save_calc = self.df_survey[
                    (drop_calc["calculation"] == self.df_survey["calculation"])
                    & (self.df_survey["type"] == "calculate")
                ]
                if len(save_calc) >= 1:
                    save_calc = save_calc.iloc[0]
                    if save_calc["name"] != drop_calc["name"]:
                        self.df_survey.replace(
                            "\$\{" + drop_calc["name"] + "\}",
                            "\$\{" + save_calc["name"] + "\}",
                            regex=True,
                        )
                else:
                    logger.error(
                        "duplicate reference not found for calculation: {}".format(
                            drop_calc["calculation"]
                        )
                    )
        for index, empty_calc in df_empty_calc.iterrows():
            self.df_survey.replace("\$\{" + empty_calc["name"] + "\}", "1", regex=True)

        # TODO try to reinject calc to reduce complexity
        for i, c in self.df_calculate[
            ~self.df_calculate["name"].isin(self.df_survey["name"])
        ].iterrows():
            real_calc = re.find(r"^number\((.+)\)$", c["calculation"])
            if real_calc is not None and real_calc != "":
                self.df_survey[~self.df_survey["name"] == c["name"]].replace(
                    real_calc, "\$\{" + c["name"] + "\}"
                )
        return processed_nodes

    def get_tricc_operation_expression(self, operation):
        ref_expressions = []
        for r in operation.reference:
            r_expr = self.get_tricc_operation_operand(r)
            if isinstance(r_expr, str) and (' or ' in r_expr or ' and ' in r_expr or \
                ' = ' in r_expr or ' < ' in r_expr or \
                ' <= ' in r_expr or ' >= ' in r_expr or \
                ' < ' in r_expr or ' != ' in r_expr):
                    r_expr = "("+r_expr+')'
            ref_expressions.append(r_expr)
        # build lower level
        if hasattr(self,f"tricc_operation_{operation.operator}"):
            callable = getattr(self,f"tricc_operation_{operation.operator}")
            return callable(ref_expressions)   
        else:
            raise NotImplementedError(f"This type of opreation '{operation.operator}' is not supported in this strategy")
        

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
        return  f"{ref_expressions[0]} >= {ref_expressions[1]} and {ref_expressions[0]} < {ref_expressions[2]}"
    def tricc_operation_equal(self, ref_expressions):
        return f"{ref_expressions[0]} = {ref_expressions[1]}"
    def tricc_operation_not_equal(self, ref_expressions):
        return f"{ref_expressions[0]} != {ref_expressions[1]}"
    def tricc_operation_case(self, ref_expressions):
        ifs = 0
        parts = []
        for i in range(int(len(ref_expressions)/2)):
            if i*2+1 <= len(ref_expressions):
                parts.append(f"if({ref_expressions[i*2]},{ref_expressions[i*2+1]}")
                ifs += 1
            else:
                parts.append(ref_expressions[i*2])
        #join the if
        exp = ','.join(parts)
        # in case there is no default put ''
        if len(ref_expressions)%2 == 0 :
            exp += ",''"
        #add the closing )
        for i in range(ifs):
            exp += ")"
        return exp
    def tricc_operation_if(self, ref_expressions):
        return self.tricc_operation_case( ref_expressions)
    def tricc_operation_contains(self, ref_expressions):
        return f"contains({ref_expressions[0]}, {ref_expressions[1]})"
    def tricc_operation_exists(self, ref_expressions):
        parts = []
        for ref in ref_expressions:
            parts.append(self.tricc_operation_not_equal([ref, "''"]))
        return self.tricc_operation_and(parts)
    # calculate or retrieve a node expression
    def get_node_expression(self, in_node, processed_nodes, is_calculate=False, is_prev=False, negate=False, ):
        # in case of calculate we only use the select multiple if none is not selected
        expression = None
        negate_expression = None
        node = in_node
        if hasattr(node, 'expression_reference') and isinstance(node.expression_reference, TriccOperation):
            expression = self.get_tricc_operation_expression(node.expression_reference)
        elif hasattr(node, 'relevance') and isinstance(node.relevance, TriccOperation):
            expression = self.get_tricc_operation_expression(node.relevance)   
        elif is_prev and isinstance(node, TriccNodeSelectOption):
            expression = get_selected_option_expression(node)
            #TODO remove that and manage it on the "Save" part
        elif is_prev and isinstance(in_node, TriccNodeSelectNotAvailable):
            expression =  TRICC_SELECTED_EXPRESSION.format(get_export_name(node), 'true()')
        elif is_prev and isinstance(node, TriccNodeRhombus):
            if node.path is not None: 
                left = self.get_node_expression(node.path, processed_nodes, is_calculate, is_prev)
            else:
                left = 'true()'
            r_ref = self.get_rhombus_terms(node, processed_nodes)  # if issubclass(node.__class__, TricNodeDisplayCalulate) else TRICC_CALC_EXPRESSION.format(get_export_name(node)) #
            expression = and_join([left, r_ref])
            negate_expression = nand_join(left, r_ref)        
        elif isinstance(node, TriccNodeWait):
            if is_prev:
                # the wait don't do any calculation with the reference it is only use to wait until the reference are valid
                return self.get_node_expression(node.path, processed_nodes, is_calculate, is_prev)
            else:
                #it is a empty calculate
                return ''
        elif is_prev and issubclass(node.__class__, TriccNodeDisplayCalculateBase):
            expression = TRICC_CALC_EXPRESSION.format(get_export_name(node))
        elif issubclass(node.__class__, TriccNodeCalculateBase):
            if negate:
                negate_expression = self.get_calculation_terms(node, processed_nodes, is_calculate, negate=True)
            else:
                expression = self.get_calculation_terms(node, processed_nodes, is_calculate)
        elif is_prev and hasattr(node, 'required') and node.required == True:
            expression = get_required_node_expression(node)

        elif is_prev and hasattr(node, 'relevance') and node.relevance is not None and node.relevance != '':
                expression = node.relevance
        if expression is None:
                expression = self.get_prev_node_expression(node, processed_nodes, is_calculate)
        if isinstance(node, TriccNodeActivity) and is_prev:
            end_nodes = node.get_end_nodes()
            if all([end in processed_nodes for end in end_nodes]):
                expression = and_join([expression, self.get_activity_end_terms(node,processed_nodes)])
        if negate:
            if negate_expression is not None:
                return negate_expression
            elif expression is not None:
                return negate_term(expression)
            else:
                logger.error("exclusive can not negate None from {}".format(node.get_name()))
                # exit()
        else:
            return expression
        
    # main function to retrieve the expression from the tree
    # node is the node to calculate
    # processed_nodes are the list of processed nodes
    def get_node_expressions(self, node, processed_nodes):
        is_calculate = issubclass(node.__class__, TriccNodeCalculateBase)
        expression = None
        # in case of recursive call processed_nodes will be None
        if processed_nodes is None or is_ready_to_process(node, processed_nodes):
            expression = self.get_node_expression(node, processed_nodes, is_calculate)
            
        if is_calculate:
            if expression is not None and expression != '':
                expression = TRICC_NUMBER.format(expression)
            else:
                expression = ''
        if issubclass(node.__class__, TriccNodeCalculateBase) and expression == '' and not isinstance(node, (TriccNodeWait, TriccNodeActivityEnd, TriccNodeActivityStart)):
            logger.warning("Calculate {0} returning no calculations".format(node.get_name()))
            expression = 'true()'
        return expression
    
    def get_prev_node_expression(self, node, processed_nodes, is_calculate=False, excluded_name=None):
        expression = None
        if node is None:
            pass
        # when getting the prev node, we calculate the
        if hasattr(node, 'expression_inputs') and len(node.expression_inputs) > 0:
            expression_inputs = node.expression_inputs
            expression_inputs = clean_list_or(expression_inputs)
        else:
            expression_inputs = []
        if isinstance(node, TriccNodeBridge) and node.label=='path: signe de danger >0  ?':
            logger.debug('hre')
        for prev_node in node.prev_nodes:
            if excluded_name is None or prev_node != excluded_name or (
                    isinstance(excluded_name, str) and hasattr(prev_node, 'name') and prev_node.name != excluded_name): # or isinstance(prev_node, TriccNodeActivityEnd):
                # the rhombus should calculate only reference
                add_sub_expression(expression_inputs, self.get_node_expression(prev_node, processed_nodes, is_calculate, True))
                # avoid void is there is not conditions to avoid looping too much itme
        expression_inputs = clean_list_or(expression_inputs)
        
        expression = or_join(expression_inputs)
        expression_inputs = None
            # if isinstance(node,  TriccNodeExclusive):
            #    expression =  TRICC_NEGATE.format(expression)
        # only used for activityStart 
        if isinstance(node, TriccNodeActivity) and node.base_instance is not None:
            activity = node
            expression_inputs = []
            #exclude base node only if the defaulf instance number is not 0
            if activity.base_instance.instance >1:
                add_sub_expression(expression_inputs, self.get_node_expression(activity.base_instance, processed_nodes, False, True))
            # relevance of the previous instance must be false to display this activity
            for past_instance in activity.base_instance.instances.values():
                if int(past_instance.root.path_len) < int(activity.root.path_len) and past_instance in processed_nodes:
                    add_sub_expression(expression_inputs, self.get_node_expression(past_instance, processed_nodes, False))         
            expression_activity = or_join(expression_inputs)
            expression = nand_join(expression, expression_activity or False)
        return expression

    def get_activity_end_terms(self, node, processed_nodes):
        end_nodes = node.get_end_nodes()
        expression_inputs = []
        for end_node in end_nodes:
            add_sub_expression(expression_inputs,
                            self.get_node_expression(end_node, processed_nodes, is_calculate=False, is_prev=True))

        return  or_join(expression_inputs)

    def get_count_terms(self, node, processed_nodes, is_calculate, negate=False):
        terms = []
        for prev_node in node.prev_nodes:
            if isinstance(prev_node, TriccNodeSelectMultiple):
                if negate:
                    terms.append(TRICC_SELECT_MULTIPLE_CALC_NONE_EXPRESSION.format(get_export_name(prev_node)))
                else:
                    terms.append(TRICC_SELECT_MULTIPLE_CALC_EXPRESSION.format(get_export_name(prev_node)))
            elif isinstance(prev_node, (TriccNodeSelectYesNo, TriccNodeSelectNotAvailable)):
                terms.append(TRICC_SELECTED_EXPRESSION.format(get_export_name(prev_node), '1'))
            elif isinstance(prev_node, TriccNodeSelectOption):
                terms.append(get_selected_option_expression(prev_node))
            else:
                if negate:
                    terms.append("number(number({0})=0)".format(
                        self.get_node_expression(prev_node, processed_nodes, is_calculate=False, is_prev=True)))
                else:
                    terms.append("number({0})".format(
                        self.get_node_expression(prev_node, processed_nodes, is_calculate=False, is_prev=True)))
        if len(terms) > 0:
            return ' + '.join(terms)
        
    def get_add_terms(self, node, processed_nodes, is_calculate=False, negate=False):
        if negate:
            logger.warning("negate not supported for Add node {}".format(node.get_name()))
        terms = []
        for prev_node in node.prev_nodes:
            if issubclass(prev_node, TriccNodeNumber) or isinstance(node, TriccNodeCount):
                terms.append("coalesce(${{{0}}},0)".format(get_export_name(prev_node)))
            else:
                terms.append(
                    "number({0})".format(self.get_node_expression(prev_node, processed_nodes, is_calculate=False, is_prev=True)))
        if len(terms) > 0:
            return ' + '.join(terms)
        
    def get_rhombus_terms(self, node, processed_nodes, is_calculate=False, negate=False):
        expression = None
        left_term = None
        # calcualte the expression only for select muzltiple and fake calculate
        if node.reference is not None and issubclass(node.reference.__class__, list):
            if node.expression_reference is None and len(node.reference) == 1:
                if node.label is not None:
                    for operation in OPERATION_LIST:
                        left_term = process_rhumbus_expression(node.label, operation)
                        if left_term is not None:
                            break
                if left_term is None:
                    left_term = '>0'
                ref = node.reference[0]
                if issubclass(ref.__class__, TriccNodeBaseModel):
                    if isinstance(ref, TriccNodeActivity):
                        expression = self.get_activity_end_terms(ref, processed_nodes)
                    elif issubclass(ref.__class__, TriccNodeFakeCalculateBase):
                        expression = self.get_node_expression(ref, processed_nodes, is_calculate=True, is_prev=True)
                    else:
                        expression = TRICC_REF_EXPRESSION.format(get_export_name(ref))
                else:
                    # expression = TRICC_REF_EXPRES
                    # SION.format(node.reference)
                    # expression = "${{{}}}".format(node.reference)
                    logger.error('reference {0} was not found in the previous nodes of node {1}'.format(node.reference,
                                                                                                        node.get_name()))
                    exit()
            elif node.expression_reference is not None and node.expression_reference != '':
                left_term = ''
                expression = node.expression_reference.format(*get_list_names(node.reference))
            else:
                logger.warning("missing epression for node {}".format(node.get_name()))
        else:
            logger.error('reference {0} is not a list {1}'.format(node.reference, node.get_name()))
            exit()

        if expression is not None:

            if left_term is not None and re.search(" (\+)|(\-)|(or)|(and) ", expression):
                expression = "({0}){1}".format(expression, left_term)
            else:
                expression = "{0}{1}".format(expression, left_term)
        else:
            logger.error("Rhombus reference was not found for node {}, reference {}".format(
                node.get_name(),
                node.reference
            ))
            exit()

        return expression
    # function that generate the calculation terms return by calculate node
    # @param node calculate node to assess
    # @param processed_nodes list of node already processed, importnat because only processed node could be use
    # @param is_calculate used when this funciton is called in the evaluation of another calculate
    # @param negate use to retriece the negation of a calculation
    def get_calculation_terms(self, node, processed_nodes, is_calculate=False, negate=False):
        # returns something directly only if the negate is managed
        expresison = None
        if isinstance(node, TriccNodeAdd):
            return self.get_add_terms(node, False, negate)
        elif isinstance(node, TriccNodeCount):
            return self.get_count_terms(node, False, negate)
        elif isinstance(node, TriccNodeRhombus):
            return self.get_rhombus_terms(node, processed_nodes, False, negate)
        elif isinstance(node, ( TriccNodeWait)):
            # just use to force order of question
            expression = None
        # in case of calulate expression evaluation, we need to get the relevance of the activity 
        # because calculate are not the the activity group
        elif isinstance(node, (TriccNodeActivityStart)) and is_calculate:
            expresison =  self.get_prev_node_expression(node.activity, processed_nodes, is_calculate)
        elif isinstance(node, (TriccNodeActivityStart, TriccNodeActivityEnd)):
            # the group have the relevance for the activity, not needed to replicate it
            expression = None#return get_prev_node_expression(node.activity, processed_nodes, is_calculate=False, excluded_name=None)
        elif isinstance(node, TriccNodeExclusive):
            if len(node.prev_nodes) == 1:
                if isinstance(node.prev_nodes[0], TriccNodeExclusive):
                    logger.error("2 exclusives cannot be on a row")
                    exit()
                elif issubclass(node.prev_nodes[0].__class__, TriccNodeCalculateBase):
                    return self.get_node_expression(node.prev_nodes[0], processed_nodes, is_prev=True, negate=True)
                elif isinstance(node.prev_nodes[0], TriccNodeActivity):
                    return self.get_node_expression(node.prev_nodes[0], processed_nodes, is_calculate=False, is_prev=True,
                                            negate=True)
                else:
                    logger.error(f"exclusive node {node.get_name()}\
                        does not depend of a calculate but on\
                            {node.prev_nodes[0].__class__}::{node.prev_nodes[0].get_name()}")

            else:
                logger.error("exclusive node {} has no ou too much parent".format(node.get_name()))
        
        if node.reference is not None and node.expression_reference is not None :
            expression = self.get_prev_node_expression(node, processed_nodes, is_calculate)
            ref_expression = node.expression_reference.format(*[get_export_name(ref) for ref in node.reference])
            if expression is not None and expression != '':
                expression =  and_join([expression,ref_expression])
            else:
                expression = ref_expression
        else:
            expression =  self.get_prev_node_expression(node, processed_nodes, is_calculate)
        
        # manage the generic negation
        if negate:
            
            return negate_term(expression)
        else:
            return expresison
        
    # function update the calcualte in the XLSFORM format
    # @param left part
    # @param right part        
    def generate_xls_form_calculate(self, node, processed_nodes, stashed_nodes, **kwargs):
        if is_ready_to_process(node, processed_nodes):
            if node not in processed_nodes:
                logger.debug("generation of calculate for node {}".format(node.get_name()))
                if hasattr(node, 'expression') and (node.expression is None) and issubclass(node.__class__,TriccNodeCalculateBase):
                    node.expression = self.get_node_expressions(node, processed_nodes)
                    # continue walk
                return True
        return False
    
    # function update the relevance in the XLSFORM format
    # @param left part
    # @param right part
    def generate_xls_form_relevance(self, node, processed_nodes, stashed_nodes, **kwargs):
        if is_ready_to_process(node, processed_nodes):
            if node not in processed_nodes:
                logger.debug('Processing relevance for node {0}'.format(node.get_name()))
                # if has prev, create condition
                if hasattr(node, 'relevance') and (node.relevance is None or isinstance(node.relevance, TriccOperation)):
                    node.relevance = self.get_node_expressions(node, processed_nodes)
                    # manage not Available
                    if isinstance(node, TriccNodeSelectNotAvailable):
                        # update the checkbox
                        if len(node.prev_nodes) == 1:
                            parent_node = node.prev_nodes[0]
                            parent_empty = "${{{0}}}=''".format(get_export_name(parent_node))
                            node.relevance  = and_join([node.relevance, parent_empty])

                            node.required = parent_empty
                            node.constraint = parent_empty
                            node.constraint_message = "Cannot be selected with a value entered above"
                            # update the check box parent : create loop error
                            parent_node.required = None  # "${{{0}}}=''".format(node.name)
                        else:
                            logger.warning("not available node {} does't have a single parent".format(node.get_name()))

                return True
        return False
    
    # function update the select node in the XLSFORM format
    # @param left part
    # @param right part
    def generate_xls_form_condition(self, node, processed_nodes, stashed_nodes, **kwargs):
        if is_ready_to_process(node, processed_nodes,   strict=False):
            if node not in processed_nodes:
                if issubclass(node.__class__, TriccRhombusMixIn) and isinstance(node.reference, str):
                    logger.warning("node {} still using the reference string".format(node.get_name()))
                if issubclass(node.__class__, TriccNodeInputModel):
                    # we don't overright if define in the diagram
                    if node.constraint is None:
                        if isinstance(node, TriccNodeSelectMultiple):
                            node.constraint = '.=\'opt_none\' or not(selected(.,\'opt_none\'))'
                            node.constraint_message = '**None** cannot be selected together with choice.'
                    elif node.tricc_type in (TriccNodeType.integer, TriccNodeType.decimal):
                        constraints = []
                        constraints_min = None
                        constraints_max = None
                        if node.min is not None:
                            constraints.append('.>=' + node.min) 
                            constraints_min= "The minimun value is {0}.".format(node.min)
                        if node.max is not None:
                            constraints.append('.>=' + node.max)
                            constraints_max="The maximum value is {0}.".format(node.max)
                        if len(constraints) > 0:
                            node.constraint = ' and '.join(constraints)
                            node.constraint_message = (constraints_min + " "  + constraints_max).strip()
                # continue walk
                return True
        return False

    # function transform an object to XLSFORM value
    # @param r reference to be translated    
    def get_tricc_operation_operand(self,r):
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
            raise NotImplementedError(f"This type of node {r.__class__} is not supported within an operation")