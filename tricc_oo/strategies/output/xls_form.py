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
    TriccOperation,
    TriccOperator
)
from tricc_oo.models.lang import SingletonLangClass

from tricc_oo.visitors.tricc import (
    check_stashed_loop,
    walktrhough_tricc_node_processed_stached,
    is_ready_to_process,
    process_reference,
    get_node_expressions,
    TRICC_TRUE_VALUE,
    TRICC_FALSE_VALUE,
    set_last_version_false
)
from tricc_oo.serializers.xls_form import (
    CHOICE_MAP,
    SURVEY_MAP,
    end_group,
    generate_xls_form_export,
    start_group,
    BOOLEAN_MAP
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
langs = SingletonLangClass()

OPERATOR_COALESCE_FALLBACK = {
    TriccOperator.ISTRUE: 0,
    TriccOperator.ISFALSE: 1,
    TriccOperator.ISNOTTRUE: 0,
    TriccOperator.ISNOTFALSE: 1,
    TriccOperator.MORE: -2147483648,
    TriccOperator.MORE_OR_EQUAL: -2147483648,
    TriccOperator.LESS: 2147483647,
    TriccOperator.LESS_OR_EQUAL: 2147483647
}

class XLSFormStrategy(BaseOutPutStrategy):
    pd.set_option('display.max_colwidth', None)
    df_survey = pd.DataFrame(columns=SURVEY_MAP.keys())
    df_calculate = pd.DataFrame(columns=SURVEY_MAP.keys())
    df_choice = pd.DataFrame(columns=CHOICE_MAP.keys())
    calculates = {}
    # add save nodes and merge nodes


    def clean_coalesce(self, expression):   
        if re.match(r"^coalesce\(\${[^}]+},''\)$", str(expression)):
            return str(expression[9:-4])
        return str(expression)

    def generate_base(self, node, **kwargs):
        return self.generate_xls_form_condition(node, **kwargs) 

    def generate_relevance(self, node, **kwargs):
        return self.generate_xls_form_relevance(node, **kwargs)

    def generate_calculate(self, node, **kwargs):
        return self.generate_xls_form_calculate(node, **kwargs)

    def __init__(self, project, output_path):
        super().__init__(project, output_path)
        self.do_clean()

    def do_clean(self, **kwargs):
        self.calculates = {}
        self.used_calculates = {}

    def get_kwargs(self):
        return {
            "df_survey": self.df_survey,
            "df_choice": self.df_choice,
            "df_calculate": self.df_calculate,
            "calculates": self.calculates
        }

    def generate_export(self, node, **kwargs):
        return generate_xls_form_export(self, node, **kwargs)


    def export(self, start_pages, version):
        if start_pages["main"].root.form_id is not None:
            form_id = str(start_pages["main"].root.form_id)
        else:
            logger.critical("form id required in the first start node")
            exit(1)
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

    def activity_export(self, activity, processed_nodes=None, **kwargs):
        if processed_nodes is None:
            processed_nodes = OrderedSet()
        stashed_nodes = OrderedSet()
        # The stashed node are all the node that have all their prevnode processed but not from the same group
        # This logic works only because the prev node are ordered by group/parent ..
        skip_header = 0
        groups = {}
        cur_group = activity
        groups[activity.id] = 0
        path_len = 0
        process = ['main']
        # keep the vesrions on the group id, max version
        start_group(self, cur_group=cur_group, groups=groups, processed_nodes=processed_nodes, process=process,  **self.get_kwargs())
        walktrhough_tricc_node_processed_stached(
            activity.root,
            self.generate_export,
            processed_nodes,
            stashed_nodes,
            path_len,
            cur_group=activity.root.group,
            process=process,
            recursive=False,
            **self.get_kwargs()
        )
        end_group(self, cur_group=activity, groups=groups, **self.get_kwargs())
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
                if s_node.group is None:
                    logger.critical(
                        "ERROR group is none for node {}".format(s_node.get_name())
                    )
                start_group(
                    self,
                    cur_group=s_node.group,
                    groups=groups,
                    processed_nodes=processed_nodes,
                    process=process,
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
                    recursive=False,
                    process = process,
                    **self.get_kwargs()
                )
                # add end group if new node where added OR if the previous end group was removed
                end_group(self, cur_group=s_node.group, groups=groups, **self.get_kwargs())
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
                        if len(df_survey_final):
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
        self.df_survey.reset_index(drop=True, inplace=True)
        self.df_calculate.reset_index(drop=True, inplace=True)
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
                            "${" + drop_calc["name"] + "}",
                            "${" + save_calc["name"] + "}",
                        )
                else:
                    logger.critical(
                        "duplicate reference not found for calculation: {}".format(
                            drop_calc["calculation"]
                        )
                    )
        for index, empty_calc in df_empty_calc.iterrows():
            self.df_survey.replace("${" + empty_calc["name"] + "}", "1", regex=True)

        # TODO try to reinject calc to reduce complexity
        for i, c in self.df_calculate[
            ~self.df_calculate["name"].isin(self.df_survey["name"])
        ].iterrows():
            real_calc = re.find(r"^number\((.+)\)$", c["calculation"])
            if real_calc is not None and real_calc != "":
                self.df_survey[~self.df_survey["name"] == c["name"]].replace(
                    real_calc, "${" + c["name"] + "}"
                )
        
        df_duplicate = self.df_survey[
            self.df_survey.duplicated(subset=["name"], keep="first")
        ]
        for index, duplicate in df_duplicate.iterrows(): 
            logger.critical(f"duplicate survey name: {duplicate['name']}")
        self.df_survey.reset_index(drop=True, inplace=True)
        return processed_nodes

    def get_tricc_operation_expression(self, operation):
        ref_expressions = []
        if not hasattr(operation, 'reference'):
            return self.get_tricc_operation_operand(operation) 
        
        operator = getattr(operation, 'operator', '')
        coalesce_fallback = OPERATOR_COALESCE_FALLBACK[operator] if operator in OPERATOR_COALESCE_FALLBACK else  "''"
        for r in operation.reference:
            if isinstance(r, list):
                r_expr = [
                    self.get_tricc_operation_expression(sr) if isinstance(sr, TriccOperation)
                    else self.get_tricc_operation_operand(sr,coalesce_fallback) 
                    for sr in r
                ]
            elif isinstance(r, TriccOperation):
                r_expr = self.get_tricc_operation_expression(r)
            else:
                r_expr = self.get_tricc_operation_operand(r,coalesce_fallback)
            if isinstance(r_expr, TriccReference):
                r_expr = self.get_tricc_operation_operand(r_expr,coalesce_fallback)
            ref_expressions.append(r_expr)
        
        # build lower level
        if hasattr(self,f"tricc_operation_{operation.operator}"):
            callable = getattr(self,f"tricc_operation_{operation.operator}")
            return callable(ref_expressions)   
        else:
            raise NotImplementedError(f"This type of opreation '{operation.operator}' is not supported in this strategy")
        
    def tricc_operation_multiplied(self, ref_expressions):
        return '*'.join(ref_expressions)
    def tricc_operation_divided(self, ref_expressions):
        return f"{ref_expressions[0]} div {ref_expressions[1]}"
    def tricc_operation_modulo(self, ref_expressions):
        return f"{ref_expressions[0]} mod {ref_expressions[1]}"
    def tricc_operation_coalesce(self, ref_expressions):
        return f"coalesce({','.join(map(self.clean_coalesce, ref_expressions))})"
    def tricc_operation_module(self, ref_expressions):
        return f"{ref_expressions[0]} mod {ref_expressions[1]}"
    def tricc_operation_minus(self, ref_expressions):
        if len(ref_expressions)>1:
            return ' - '.join(map(str,ref_expressions))
        elif len(ref_expressions)==1:
            return f'-{ref_expressions[0]}'
    def tricc_operation_plus(self, ref_expressions):
        return ' + '.join(ref_expressions)
    def tricc_operation_not(self, ref_expressions):
        return f"not({ref_expressions[0]})"
    def tricc_operation_and(self, ref_expressions):
        if len(ref_expressions) == 1:
            return ref_expressions[0]
        if len(ref_expressions)>1: 
            ref_expressions = [f"({r})" if isinstance(r, str) and any(op in r for op in [' or ',' + ',' - '])else r for r in ref_expressions]
            return ' and '.join(map(str, ref_expressions))
        else:
            return '1'

    def tricc_operation_or(self, ref_expressions):
        if len(ref_expressions) == 1:
            return ref_expressions[0]
        if len(ref_expressions)>1: 
            ref_expressions = [f"({r})" if isinstance(r, str) and any(op in r for op in [' and ',' + ',' - ']) else r for r in ref_expressions]
            return ' or '.join(map(str, ref_expressions))
        else:
            return '1'



    def tricc_operation_native(self, ref_expressions):
        if len(ref_expressions)>0:
            if ref_expressions[0] =='GetChoiceName':
                return f"jr:choice-name({self.clean_coalesce(ref_expressions[1])}, '{self.clean_coalesce(ref_expressions[2])}')"
            elif ref_expressions[0] =='GetFacilityParam':
                return '0'
                #return f"jr:choice-name({','.join(ref_expressions[1:])})"
            else: 
                return f"{ref_expressions[0]}({','.join(ref_expressions[1:])})"
        
    def tricc_operation_istrue(self, ref_expressions):
        if str(BOOLEAN_MAP[str(TRICC_TRUE_VALUE)]).isnumeric():
            return f"{ref_expressions[0]}>={BOOLEAN_MAP[str(TRICC_TRUE_VALUE)]}"
        else:
            return f"{ref_expressions[0]}={BOOLEAN_MAP[str(TRICC_TRUE_VALUE)]}"
    def tricc_operation_isfalse(self, ref_expressions):
        if str(BOOLEAN_MAP[str(TRICC_FALSE_VALUE)]).isnumeric():
            return f"{ref_expressions[0]}={BOOLEAN_MAP[str(TRICC_FALSE_VALUE)]}"
        else:
            return f"{ref_expressions[0]}={BOOLEAN_MAP[str(TRICC_FALSE_VALUE)]}"
    def tricc_operation_parenthesis(self, ref_expressions):
        return f"({ref_expressions[0]})"
    def tricc_operation_selected(self, ref_expressions):
        parts = []
        for s in ref_expressions[1:]:
            # for option with numeric value
            cleaned_s = s if isinstance(s, str)  else '\''+str(s)+'\''
            parts.append(f"selected({self.clean_coalesce(ref_expressions[0])}, {cleaned_s})")
        if len(parts) == 1:
            return parts[0]
        else:
            return self.tricc_operation_or(parts)
    def tricc_operation_more_or_equal(self, ref_expressions):
        return f"{ref_expressions[0]}>={ref_expressions[1]}"
    def tricc_operation_less_or_equal(self, ref_expressions):
        return f"{ref_expressions[0]}<={ref_expressions[1]}"
    def tricc_operation_more(self, ref_expressions):
        return f"{ref_expressions[0]}>{ref_expressions[1]}"
    def tricc_operation_less(self, ref_expressions):
        return f"{ref_expressions[0]}<{ref_expressions[1]}"
    def tricc_operation_between(self, ref_expressions):
        return  f"{ref_expressions[0]}>={ref_expressions[1]} and {ref_expressions[0]} < {ref_expressions[2]}"
    def tricc_operation_equal(self, ref_expressions):
        return f"{ref_expressions[0]}={ref_expressions[1]}"
    def tricc_operation_not_equal(self, ref_expressions):
        return f"{ref_expressions[0]}!={ref_expressions[1]}"
    def tricc_operation_isnull(self, ref_expressions):
        return f"{ref_expressions[0]}=''"
    def tricc_operation_isnotnull(self, ref_expressions):
        return f"{ref_expressions[0]}!=''"
    
    def tricc_operation_isnottrue(self, ref_expressions):
        if str(BOOLEAN_MAP[str(TRICC_TRUE_VALUE)]).isnumeric():
            return f"{ref_expressions[0]}<{BOOLEAN_MAP[str(TRICC_TRUE_VALUE)]}"
        else:
            return f"{ref_expressions[0]}!={BOOLEAN_MAP[str(TRICC_TRUE_VALUE)]}"
    def tricc_operation_isnotfalse(self, ref_expressions):
        if str(BOOLEAN_MAP[str(TRICC_FALSE_VALUE)]).isnumeric():
            return f"{ref_expressions[0]}>{BOOLEAN_MAP[str(TRICC_FALSE_VALUE)]}"
        else:
            return f"{ref_expressions[0]}!={BOOLEAN_MAP[str(TRICC_FALSE_VALUE)]}"
    def tricc_operation_notexist(self, ref_expressions):
        return f"{ref_expressions[0]}=''"

    
    
    def tricc_operation_case(self, ref_expressions):
        ifs = 0
        parts = []
        else_found = False
        if not isinstance(ref_expressions[0], list):
            return self.tricc_operation_ifs(ref_expressions)
        for i in range(int(len(ref_expressions))):
            if isinstance(ref_expressions[i], list):
                parts.append(f"if({ref_expressions[i][0]},{ref_expressions[i][1]}")
                ifs += 1
            else:
                else_found = True
                parts.append(ref_expressions[i])
        #join the if
        exp = ','.join(map(str,parts))
        # in case there is no default put ''
        if not else_found:
            exp += ",''"
        #add the closing )
        for i in range(ifs):
            exp += ")"
        return exp
    
    def tricc_operation_ifs(self, ref_expressions):
        ifs = 0
        parts = []
        else_found = False
        for i in range(int(len(ref_expressions[1:]))):
            if isinstance(ref_expressions[i+1], list):
                parts.append(f"if({ref_expressions[0]}={ref_expressions[i+1][0]},{ref_expressions[i+1][1]}")
                ifs += 1
            else:
                else_found = True
                parts.append(ref_expressions[i+1])
        #join the if
        exp = ','.join(parts)
        # in case there is no default put ''
        if not else_found:
            exp += ",''"
        #add the closing )
        for i in range(ifs):
            exp += ")"
        return exp
    
    def tricc_operation_if(self, ref_expressions):
        return f"if({ref_expressions[0]},{ref_expressions[1]},{ref_expressions[2]})"
    
    def tricc_operation_contains(self, ref_expressions):
        return f"contains('{self.clean_coalesce(ref_expressions[0])}', '{self.clean_coalesce(ref_expressions[1])}')"
    
    def tricc_operation_exists(self, ref_expressions):
        parts = []
        for ref in ref_expressions:
            parts.append(self.tricc_operation_not_equal([self.tricc_operation_coalesce([ref, "''"]), "''"]))
        return self.tricc_operation_and(parts)
    
    def tricc_operation_cast_number(self, ref_expressions):
        if isinstance(ref_expressions[0], (int, float,)):
            return f"{ref_expressions[0]}"
        elif not ref_expressions or ref_expressions[0] == '':
            logger.warning("empty cast number")
            return '0'
        elif ref_expressions[0] == 'true' or ref_expressions[0] is True or ref_expressions[0] == BOOLEAN_MAP[str(TRICC_TRUE_VALUE)]:
            return 1
        elif ref_expressions[0] == 'false' or ref_expressions[0] is False or ref_expressions[0] == BOOLEAN_MAP[str(TRICC_FALSE_VALUE)]:
            return 0
        else:
            return f"number({ref_expressions[0]})"
        
    def tricc_operation_cast_integer(self, ref_expressions):
        if isinstance(ref_expressions[0], (int, float,)):
            return f"{ref_expressions[0]}"
        elif not ref_expressions or ref_expressions[0] == '':
            logger.warning("empty cast number")
            return '0'
        elif ref_expressions[0] == 'true' or ref_expressions[0] is True or ref_expressions[0] == BOOLEAN_MAP[str(TRICC_TRUE_VALUE)]:
            return 1
        elif ref_expressions[0] == 'false' or ref_expressions[0] is False or ref_expressions[0] == BOOLEAN_MAP[str(TRICC_FALSE_VALUE)]:
            return 0
        else:
            return f"int({ref_expressions[0]})"   
    def tricc_operation_zscore(self, ref_expressions):
        y, ll, m, s = self.get_zscore_params(ref_expressions)
        #  return ((Math.pow((y / m), l) - 1) / (s * l));
        return f"(pow({y} div ({m}), {ll}) -1) div (({s}) div ({ll}))"
   
    
    def tricc_operation_izscore(self, ref_expressions):
        z, ll, m, s = self.get_zscore_params(ref_expressions)
        #  return  (m * (z*s*l-1)^(1/l));
        return f"pow({m} * ({z} * {s} * {ll} -1), 1 div {ll})"
    
    def get_zscore_params(self, ref_expressions):
        table = ref_expressions[0]
        sex = clean_name(ref_expressions[1])
        x = clean_name(ref_expressions[2])
        yz = clean_name(ref_expressions[3])
        ll = (
            f"number(instance({table})/root/item[sex={sex} and x_max>"
            + x
            + " and x_min<="
            + x
            + "]/l)"
        )
        m = (
            f"number(instance({table})/root/item[sex={sex} and x_max>"
            + x
            + " and x_min<="
            + x
            + "]/m)"
        )
        s = (
            f"number(instance({table})/root/item[sex={sex} and x_max>"
            + x
            + " and x_min<="
            + x
            + "]/s)"
        )
        return yz, ll, m, s 
    
    
        
    # function update the calcualte in the XLSFORM format
    # @param left part
    # @param right part        
    def generate_xls_form_calculate(self, node, processed_nodes, stashed_nodes, calculates, **kwargs):
        if is_ready_to_process(node, processed_nodes, strict=False) and process_reference(node, processed_nodes, calculates, replace_reference=False, codesystems= kwargs.get('codesystems', None)):
            if node not in processed_nodes:
                if kwargs.get('warn', True):          
                    logger.debug("generation of calculate for node {}".format(node.get_name()))
                if hasattr(node, 'expression') and (node.expression is None) and issubclass(node.__class__,TriccNodeCalculateBase):
                    node.expression = get_node_expressions(node, processed_nodes, process=kwargs.get('process', 'main '))
                    # continue walk
                if issubclass(node.__class__, (TriccNodeDisplayModel, TriccNodeDisplayCalculateBase, TriccNodeEnd)):
                    last_version =  set_last_version_false(node, processed_nodes)
                return True
        return False
    
    # function update the select node in the XLSFORM format
    # @param left part
    # @param right part
    def generate_xls_form_condition(self, node, processed_nodes, stashed_nodes, calculates, **kwargs):
        if is_ready_to_process(node, processed_nodes, strict=False) and process_reference(node, processed_nodes, calculates, replace_reference=False, codesystems= kwargs.get('codesystems', None)):
            if node not in processed_nodes:
                if issubclass(node.__class__, TriccRhombusMixIn) and isinstance(node.reference, str):
                    logger.warning("node {} still using the reference string".format(node.get_name()))
                if issubclass(node.__class__, TriccNodeInputModel):
                    # we don't overright if define in the diagram
                    if node.constraint is None:
                        if isinstance(node, TriccNodeSelectMultiple):
                            node.constraint = or_join(
                                [
                                    TriccOperation(TriccOperator.EQUAL, ['$this', TriccStatic('opt_none')]),
                                    TriccOperation(TriccOperator.NOT, [
                                        TriccOperation(TriccOperator.SELECTED,
                                            [
                                                '$this', TriccStatic('opt_none')
                                            ])
                                ])
                                 ]
                                )#'.=\'opt_none\' or not(selected(.,\'opt_none\'))'
                            node.constraint_message = '**None** cannot be selected together with choice.'
                        elif node.tricc_type in (TriccNodeType.integer, TriccNodeType.decimal):
                            constraints = []
                            constraints_min = ''
                            constraints_max = ''
                            if node.min is not None and node.min != '':
                                constraints.append(TriccOperation(TriccOperator.MORE_OR_EQUAL, ['$this', node.min])) 
                                constraints_min= "The minimun value is {0}.".format(node.min)
                            if node.max is not None and node.max != '':
                                constraints.append(TriccOperation(TriccOperator.LESS_OR_EQUAL, ['$this', node.max])) 
                                constraints_max="The maximum value is {0}.".format(node.max)
                            if len(constraints) > 1:
                                node.constraint = TriccOperation(TriccOperator.AND, constraints)
                                node.constraint_message = (constraints_min + " "  + constraints_max).strip()
                            elif len(constraints) == 1:
                                node.constraint = constraints[0]
                                node.constraint_message = (constraints_min + " "  + constraints_max).strip()
                # continue walk
                return True
        return False

    # function transform an object to XLSFORM value
    # @param r reference to be translated    
    def get_tricc_operation_operand(self,r, coalesce_fallback="''"):
        if isinstance(r, TriccOperation):
            return self.get_tricc_operation_expression(r) 
        elif isinstance(r, TriccReference):
            logger.warning(f"reference still used in the calculate {r.value}")
            return f"${{{get_export_name(r.value)}}}" 
        elif isinstance(r, TriccStatic):
            if isinstance(r.value, bool) :#or r.value in ('true', 'false')
                return BOOLEAN_MAP[str(TRICC_TRUE_VALUE)] if r.value else BOOLEAN_MAP[str(TRICC_FALSE_VALUE)]
            if r.value == TRICC_TRUE_VALUE:
                return BOOLEAN_MAP[str(TRICC_TRUE_VALUE)]
            if r.value == TRICC_FALSE_VALUE:
                return BOOLEAN_MAP[str(TRICC_FALSE_VALUE)]
            if isinstance(r.value, str):
                return f"'{r.value}'"
            else:
                return str(r.value)
        elif isinstance(r, str):
            return f"{r}" 
        elif isinstance(r, (int, float)):
            return str(r)
        elif isinstance(r, TriccNodeSelectOption):
            logger.warning(f"select option {r.get_name()} from {r.select.get_name()} was used as a reference")
            return f"'{r.name}'"
        elif issubclass(r.__class__, TriccNodeInputModel):
            return f"coalesce(${{{get_export_name(r)}}},{coalesce_fallback})"
        elif issubclass(r.__class__, TriccNodeBaseModel):
            return f"${{{get_export_name(r)}}}"
        else:
            raise NotImplementedError(f"This type of node {r.__class__} is not supported within an operation")

    def tricc_operation_concatenate(self, ref_expressions):
        return f"concat({','.join(ref_expressions)})"