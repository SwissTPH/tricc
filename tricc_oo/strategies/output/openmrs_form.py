import logging
import os
import json
import uuid
from tricc_oo.visitors.tricc import (
    is_ready_to_process,
    process_reference,
    generate_base,
    generate_calculate,
    walktrhough_tricc_node_processed_stached,
    check_stashed_loop,
)
from tricc_oo.converters.tricc_to_xls_form import get_export_name
import datetime
from tricc_oo.strategies.output.base_output_strategy import BaseOutPutStrategy
from tricc_oo.models.base import (
    not_clean, TriccOperation,
    TriccStatic, TriccReference
)
from tricc_oo.models.tricc import (
    TriccNodeSelectOption,
    TriccNodeInputModel,
    TriccNodeBaseModel,
    TriccNodeSelect,
    TriccNodeDisplayModel,
)

from tricc_oo.models.calculate import TriccNodeDisplayCalculateBase, TriccNodeDiagnosis
from tricc_oo.models.ordered_set import OrderedSet

logger = logging.getLogger("default")

# Namespace for deterministic UUIDs
UUID_NAMESPACE = uuid.UUID('12345678-1234-5678-9abc-def012345678')

CIEL_YES = "1065AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA"
CIEL_NO = "1066AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA"


class OpenMRSStrategy(BaseOutPutStrategy):
    processes = ["main"]
    project = None
    output_path = None

    def __init__(self, project, output_path):
        super().__init__(project, output_path)
        form_id = getattr(self.project.start_pages["main"], 'form_id', 'openmrs_form')
        self.form_data = {
            "$schema": "http://json.openmrs.org/form.schema.json",
            "name": form_id,
            "uuid": str(uuid.uuid5(UUID_NAMESPACE, form_id)),
            "encounterType": str(uuid.uuid5(UUID_NAMESPACE, f"{form_id}_encounter_type")),
            "processor": "EncounterFormProcessor",
            "published": False,
            "retired": False,
            "version": "1.0",
            "availableIntents": [
                {
                    "intent": "*",
                    "display": form_id
                }
            ],
            "referencedForms": [],
            "encounter": form_id,
            "pages": []
        }
        self.field_counter = 1
        self.questions_temp = []  # Temporary storage for questions with ordering info
        self.processing_order = 0  # Counter to track processing order
        self.current_segment = None
        self.current_activity = None
        self.concept_map = {}
        self.calculated_fields = []  # Store calculated fields to add to first section of each page
        self.calculated_fields_added = set()  # Track which pages have had calculated fields added
        self.inject_version()

    def get_export_name(self, r):
        if isinstance(r, TriccNodeSelectOption):
            return self.get_option_value(r.name)
        elif isinstance(r, str):
            return self.get_option_value(r)
        elif isinstance(r, TriccStatic):
            if isinstance(r.value, str):
                return self.get_option_value(r.value)
            elif isinstance(r.value, bool):
                return str(r.value).lower()
            else:
                return r.value
        else:
            return get_export_name(r)  # Assuming r is a node

    def generate_id(self, name):
        return str(uuid.uuid5(UUID_NAMESPACE, name))

    def get_option_value(self, option_name):
        if option_name == 'true':
            return TriccStatic(True)
        elif option_name == 'false':
            return TriccStatic(False)
        return self.concept_map.get(option_name, option_name)

    def get_tricc_operation_expression(self, operation):
        # Similar to HTML, but for JSON, perhaps convert to string expressions
        ref_expressions = []
        if not hasattr(operation, "reference"):
            return self.get_tricc_operation_operand(operation)
        for r in operation.reference:
            if isinstance(r, list):
                r_expr = [
                    (
                        self.get_tricc_operation_expression(sr)
                        if isinstance(sr, TriccOperation)
                        else self.get_tricc_operation_operand(sr)
                    )
                    for sr in r
                ]
            elif isinstance(r, TriccOperation):
                r_expr = self.get_tricc_operation_expression(r)
            else:
                r_expr = self.get_tricc_operation_operand(r)
            if isinstance(r_expr, TriccReference):
                r_expr = self.get_tricc_operation_operand(r_expr)
            elif isinstance(r_expr, TriccStatic) and isinstance(r_expr.value, bool):
                r_expr = str(r_expr.value).lower()
            ref_expressions.append(r_expr)

        # build lower level
        if hasattr(self, f"tricc_operation_{operation.operator}"):
            callable = getattr(self, f"tricc_operation_{operation.operator}")
            return callable(ref_expressions)
        else:
            raise NotImplementedError(
                f"This type of operation '{operation.operator}' is not supported in this strategy"
            )

    def execute(self):
        version = datetime.datetime.now().strftime("%Y%m%d%H%M")
        logger.info(f"build version: {version}")
        if "main" in self.project.start_pages:
            self.process_base(self.project.start_pages, pages=self.project.pages, version=version)
        else:
            logger.critical("Main process required")

        logger.info("generate the relevance based on edges")
        # self.process_relevance(self.project.start_pages, pages=self.project.pages)

        logger.info("generate the calculate based on edges")
        self.process_calculate(self.project.start_pages, pages=self.project.pages)

        logger.info("generate the export format")
        self.process_export(self.project.start_pages, pages=self.project.pages)

        logger.info("create calculation page")
        self.create_calculation_page()

        logger.info("print the export")
        self.export(self.project.start_pages, version=version)

    def map_tricc_type_to_rendering(self, node):
        mapping = {
            'text': 'text',
            'integer': 'number',
            'decimal': 'number',
            'date': 'date',
            'datetime': 'datetime',
            'select_one': 'select',
            'select_multiple': 'multiCheckbox',
            'select_yesno': 'select',
            'not_available': 'checkbox',
            'note': 'markdown'
        }

        # if issubclass(node.__class__, TriccNodeSelectYesNo):
        #     return 'select'
        return mapping.get(node.tricc_type, 'text')

    def generate_base(self, node, processed_nodes, **kwargs):
        if generate_base(node, processed_nodes, **kwargs):
            if getattr(node, 'name', '') not in ('true', 'false'):
                self.concept_map[node.name] = self.generate_id(self.get_export_name(node))
            return True
        return False

    def generate_question(self, node):
        if issubclass(node.__class__, TriccNodeDisplayModel) and not isinstance(node, TriccNodeSelectOption):
            question = {
                "label": getattr(node, 'label', '').replace('\u00a0', ' ').strip(),
                "type": "obs" if issubclass(node.__class__, TriccNodeInputModel) else 'control',
                "questionOptions": {
                    "rendering": self.map_tricc_type_to_rendering(node),
                    "concept": self.generate_id(self.get_export_name(node))
                },
                "required": bool(getattr(node, 'required', False)),
                "unspecified": False,
                "id": self.get_export_name(node),
                "uuid": self.generate_id(self.get_export_name(node))
            }
            if node.image:
                question['questionOptions']["imageUrl"] = node.image
            if node.hint:
                question["questionInfo"] = node.hint
            if node.tricc_type in ['select_one', 'select_multiple']:
                # labelTrue = None
                # labelFalse = None
                # Add answers if options
                if hasattr(node, 'options'):
                    answers = []
                    for opt in node.options.values():
                        display = getattr(opt, 'label', opt.name)
                        # All options now use UUIDs
                        concept_val = self.get_option_value(opt.name)
                        if concept_val == TriccStatic(False):
                            concept_val = CIEL_NO
                            # labelFalse = display
                        if concept_val == TriccStatic(True):
                            concept_val = CIEL_YES
                            # labelTrue = display
                        answers.append({
                            "label": display,
                            "concept": concept_val,
                            })
                    question["questionOptions"]["answers"] = answers
                else:
                    question["questionOptions"]["answers"] = []
                # Set concept for the question itself if it's a coded question
                # if issubclass(node.__class__, TriccNodeSelectYesNo):
                #     question["questionOptions"]["toggleOptions"] = {
                #         "labelTrue": labelTrue,
                #         "labelFalse": labelFalse
                #     }

            relevance = None
            if hasattr(node, 'relevance') and node.relevance:
                relevance = node.relevance
            if hasattr(node, 'expression') and node.expression:
                relevance = node.expression
            if relevance:
                relevance_str = self.convert_expression_to_string(not_clean(relevance))
                if relevance_str and relevance_str != 'false':
                    question["hide"] = {
                        "hideWhenExpression": f"{relevance_str}"
                    }
            return question
        elif issubclass(node.__class__, TriccNodeDisplayCalculateBase):
            expression = getattr(node, 'expression', None)
            if expression:
                question = {
                    "id": self.get_export_name(node),
                    "type": "obs" if isinstance(node, TriccNodeDiagnosis) else "control",
                    "label": getattr(node, 'label', '').replace('\u00a0', ' ').strip(),
                    "hide": {
                        "hideWhenExpression": "true"
                    },
                    "questionOptions": {
                        "calculate": {
                            "calculateExpression": self.convert_expression_to_string(expression)
                        }
                    }
                }
                # Collect calculated fields to add to first section of each page
                self.calculated_fields.append(question)
                return None  # Don't return the question, it will be added to first section
        return None

    def generate_calculate(self, node, processed_nodes, **kwargs):
        return generate_calculate(node, processed_nodes, **kwargs)

    def process_export(self, start_pages, **kwargs):
        self.activity_export(start_pages["main"], **kwargs)

    def activity_export(self, activity, processed_nodes=None, **kwargs):
        if processed_nodes is None:
            processed_nodes = OrderedSet()
        stashed_nodes = OrderedSet()
        # The stashed node are all the node that have all their prevnode processed but not from the same group
        # This logic works only because the prev node are ordered by group/parent ..
        groups = {}
        cur_group = activity
        groups[activity.id] = 0
        path_len = 0
        process = ["main"]
        # keep the versions on the group id, max version
        self.start_page(cur_group)
        self.start_section(cur_group)
        walktrhough_tricc_node_processed_stached(
            activity.root,
            self.generate_export,
            processed_nodes,
            stashed_nodes,
            path_len,
            cur_group=activity.root.group,
            process=process,
            recursive=False,
            **kwargs
        )
        # we save the survey data frame
        # MANAGE STASHED NODES
        prev_stashed_nodes = stashed_nodes.copy()
        loop_count = 0
        len_prev_processed_nodes = 0
        while len(stashed_nodes) > 0:
            self.questions_temp = []  # Reset for new section
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
                    logger.critical("ERROR group is none for node {}".format(s_node.get_name()))
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
                    process=process,
                    **kwargs
                )
                # add end group if new node where added OR if the previous end group was removed
                # if two line then empty group
                if len(self.questions_temp) > 0:
                    # Add questions to current section
                    for q_item in sorted(self.questions_temp, key=lambda x: x['processing_order']):
                        if self.current_section:
                            self.current_section["questions"].append(q_item['question'])
                    cur_group = s_node.group

        return processed_nodes

    def generate_export(self, node, processed_nodes, **kwargs):
        if not is_ready_to_process(node, processed_nodes, strict=False):
            return False

        # Process references to ensure dependencies are handled
        if not process_reference(
            node, processed_nodes, {}, replace_reference=False, codesystems=kwargs.get("codesystems", None)
        ):
            return False

        if node not in processed_nodes:
            if self.current_segment != getattr(node.activity.root, 'process', self.current_segment):
                self.start_page(node.activity)
            if self.current_activity != node.group:
                self.start_section(node.activity)
            question = self.generate_question(node)
            if question:
                # Store question with processing order
                # self.questions_temp.append({
                #     'question': question,
                #     'processing_order': self.processing_order,
                #     'node_id': getattr(node, 'id', '')
                # })
                self.processing_order += 1
                self.field_counter += 1
                self.form_data['pages'][-1]['sections'][-1]['questions'].append(question)

        # Set form name from the start page label if available
        if hasattr(self.project.start_pages["main"], 'label') and self.project.start_pages["main"].label:
            self.form_data["name"] = self.project.start_pages["main"].label.strip()
        elif hasattr(node, 'label') and node.label:
            self.form_data["name"] = node.label.strip()
        return True

    def export(self, start_pages, version):
        form_id = start_pages["main"].root.form_id or "openmrs_form"
        file_name = f"{form_id}.json"
        newpath = os.path.join(self.output_path, file_name)
        if not os.path.exists(self.output_path):
            os.makedirs(self.output_path)

        with open(newpath, 'w') as f:
            json.dump(self.form_data, f, indent=2)
        logger.info(f"Exported OpenMRS form to {newpath}")

    def get_tricc_operation_operand(self, r):
        if isinstance(r, TriccOperation):
            return self.get_tricc_operation_expression(r)
        elif isinstance(r, TriccReference):
            return self.get_export_name(r.value)
        elif isinstance(r, TriccStatic):
            if isinstance(r.value, bool):
                return str(r.value).lower()
            if isinstance(r.value, str):
                return f"'{r.value}'"
            else:
                return str(r.value)
        elif isinstance(r, bool):
            return str(r).lower()
        elif isinstance(r, str):
            return f"{r}"
        elif isinstance(r, (int, float)):
            return str(r).lower()
        elif isinstance(r, TriccNodeSelectOption):
            option = self.get_option_value(r.name)
            if r.name in ('true', 'false'):
                return option
            return f"'{option}'"
        elif issubclass(r.__class__, TriccNodeInputModel):
            return self.get_export_name(r)
        elif issubclass(r.__class__, TriccNodeSelect):
            return "(" + self.get_export_name(r) + " ?? [])"       
        elif issubclass(r.__class__, TriccNodeBaseModel):
            return self.get_export_name(r)
        else:
            raise NotImplementedError(f"This type of node {r.__class__} is not supported within an operation")

    def convert_expression_to_string(self, expression):
        # Convert to string expression for JSON
        if isinstance(expression, TriccOperation):
            return self.get_tricc_operation_expression(expression)
        else:
            return self.get_tricc_operation_operand(expression)

    # Operation methods similar, but for string expressions
    def tricc_operation_equal(self, ref_expressions):
        if ref_expressions[1] == TriccStatic(True) or ref_expressions[1] is True or ref_expressions[1] == 'true':
            return f"{self._boolean(ref_expressions, '===', CIEL_YES, 'true')}"
        elif ref_expressions[1] == TriccStatic(False) or ref_expressions[1] is False or ref_expressions[1] == 'false':
            return f"{self._boolean(ref_expressions, '===', CIEL_NO, 'false')}"
        return f"{ref_expressions[0]} === {ref_expressions[1]}"

    def tricc_operation_not_equal(self, ref_expressions):
        if ref_expressions[1] == TriccStatic(True) or ref_expressions[1] is True or ref_expressions[1] == 'true':
            return f"!{self._boolean(ref_expressions, '===', CIEL_YES, 'true')}"
        elif ref_expressions[1] == TriccStatic(False) or ref_expressions[1] is False or ref_expressions[1] == 'false':
            return f"!{self._boolean(ref_expressions, '===', CIEL_NO, 'false')}"
        return f"{ref_expressions[0]} !== {ref_expressions[1]}"

    def tricc_operation_and(self, ref_expressions):
        if len(ref_expressions) == 1:
            return ref_expressions[0]
        if len(ref_expressions) > 1:
            return " && ".join(ref_expressions)
        else:
            return "true"

    def tricc_operation_or(self, ref_expressions):
        if len(ref_expressions) == 1:
            return ref_expressions[0]
        if len(ref_expressions) > 1:
            return "(" + " || ".join(ref_expressions) + ")"
        else:
            return "true"

    def tricc_operation_not(self, ref_expressions):
        return f"!({ref_expressions[0]})"

    def tricc_operation_plus(self, ref_expressions):
        return "(" + " + ".join(ref_expressions) +")" 

    def tricc_operation_minus(self, ref_expressions):
        if len(ref_expressions) > 1:
            return " - ".join(map(str, ref_expressions))
        elif len(ref_expressions) == 1:
            return f"-{ref_expressions[0]}"

    def tricc_operation_more(self, ref_expressions):
        return f"{ref_expressions[0]} > {ref_expressions[1]}"

    def tricc_operation_less(self, ref_expressions):
        return f"{ref_expressions[0]} < {ref_expressions[1]}"

    def tricc_operation_more_or_equal(self, ref_expressions):
        return f"{ref_expressions[0]} >= {ref_expressions[1]}"

    def tricc_operation_less_or_equal(self, ref_expressions):
        return f"{ref_expressions[0]} <= {ref_expressions[1]}"

    def tricc_operation_selected(self, ref_expressions):
        # For choice questions, returns true if the second reference (value) is included in the first (field)
        return f"({ref_expressions[0]}.includes({ref_expressions[1]}))"

    def tricc_operation_count(self, ref_expressions):
        return f"{ref_expressions[0]}.length"

    def tricc_operation_multiplied(self, ref_expressions):
        return "*".join(ref_expressions)

    def tricc_operation_divided(self, ref_expressions):
        return f"{ref_expressions[0]} / {ref_expressions[1]}"

    def tricc_operation_modulo(self, ref_expressions):
        return f"{ref_expressions[0]} % {ref_expressions[1]}"

    def tricc_operation_coalesce(self, ref_expressions):
        return f"coalesce({','.join(ref_expressions)})"

    def tricc_operation_module(self, ref_expressions):
        return f"{ref_expressions[0]} % {ref_expressions[1]}"

    def tricc_operation_native(self, ref_expressions):
        if len(ref_expressions) > 0:
            return f"{ref_expressions[0]}({','.join(ref_expressions[1:])})"

    def tricc_operation_istrue(self, ref_expressions):
        # return f"{ref_expressions[0]} === true"
        return f"{self._boolean(ref_expressions, '===', CIEL_YES, 'true')}"

    def tricc_operation_isfalse(self, ref_expressions):
        # return f"{ref_expressions[0]} === false"
        return f"{self._boolean(ref_expressions, '===', CIEL_NO, 'false')}"

    def tricc_operation_parenthesis(self, ref_expressions):
        return f"({ref_expressions[0]})"

    def tricc_operation_between(self, ref_expressions):
        return f"{ref_expressions[0]} >= {ref_expressions[1]} && {ref_expressions[0]} < {ref_expressions[2]}"

    def tricc_operation_isnull(self, ref_expressions):
        return f"isEmpty({ref_expressions[0]})"

    def tricc_operation_isnotnull(self, ref_expressions):
        return f"!isEmpty{ref_expressions[0]})"

    def tricc_operation_isnottrue(self, ref_expressions):
        # return f"{ref_expressions[0]} !== true"
        return f"!{self._boolean(ref_expressions, '===', CIEL_YES, 'true')}"

    def tricc_operation_isnotfalse(self, ref_expressions):
        # return f"{ref_expressions[0]} !== false"
        return f"!{self._boolean(ref_expressions, '===', CIEL_NO, 'false')}"

    def _boolean(self, ref_expressions, operator, answer_uuid, bool_val='false'):
        return f"({ref_expressions[0]} {operator} {bool_val} || {ref_expressions[0]} {operator} '{answer_uuid}')"

    def tricc_operation_notexist(self, ref_expressions):
        return f"typeof {ref_expressions[0]} === 'undefined'"

    def tricc_operation_case(self, ref_expressions):
        # Simplified, assuming list of conditions
        parts = []
        for i in range(0, len(ref_expressions), 2):
            if i + 1 < len(ref_expressions):
                parts.append(f"if({ref_expressions[i]}, {ref_expressions[i+1]})")
        return " || ".join(parts)  # Simplified

    def tricc_operation_ifs(self, ref_expressions):
        # Similar to case
        return self.tricc_operation_case(ref_expressions[1:])

    def tricc_operation_if(self, ref_expressions):
        return f"if({ref_expressions[0]}, {ref_expressions[1]}, {ref_expressions[2]})"

    def tricc_operation_contains(self, ref_expressions):
        return f"contains({ref_expressions[0]}, {ref_expressions[1]})"

    def tricc_operation_exists(self, ref_expressions):
        parts = []
        for ref in ref_expressions:
            parts.append(f"!isEmpty{ref})")
        return " && ".join(parts)

    def tricc_operation_cast_number(self, ref_expressions):
        return f"Number({ref_expressions[0]})"

    def tricc_operation_cast_integer(self, ref_expressions):
        return f"Number({ref_expressions[0]})"

    def tricc_operation_zscore(self, ref_expressions):
        # Simplified, assuming params
        return f"zscore({','.join(ref_expressions)})"

    def tricc_operation_datetime_to_decimal(self, ref_expressions):
        return f"decimal-date-time({ref_expressions[0]})"

    def tricc_operation_round(self, ref_expressions):
        return f"round({ref_expressions[0]})"

    def tricc_operation_izscore(self, ref_expressions):
        return f"izscore({','.join(ref_expressions)})"

    def tricc_operation_concatenate(self, ref_expressions):
        return f"concat({','.join(ref_expressions)})"

    def clean_sections(self):
        if (
            self.form_data['pages']
            and self.form_data['pages'][-1]
            and self.form_data['pages'][-1]['sections']
            and self.form_data['pages'][-1]['sections'][-1]
        ):
            if len(self.form_data['pages'][-1]['sections'][-1]['questions']) == 0:
                self.form_data['pages'][-1]['sections'].pop()

    def clean_pages(self):
        if self.form_data['pages'] and self.form_data['pages'][-1]:
            if len(self.form_data['pages'][-1]['sections']) == 0:
                self.form_data['pages'].pop()

    def start_page(self, activity_node):
        # Add more operations as needed...
        """Start a new page for an activity"""
        self.clean_sections()
        self.clean_pages()
        page_label = getattr(activity_node.root, 'process', None)
        self.current_segment = page_label
        # Set process from id if not set
        default_label = f"Page {len(self.form_data['pages']) + 1}"

        if page_label is None:
            label = getattr(activity_node, 'label', None)
            if label is None:
                page_label = default_label
            else:
                page_label = label
        page_label = page_label.replace('\u00a0', ' ').strip()
        self.form_data["pages"].append({
            "label": page_label,
            "sections": []
        })
        if activity_node.relevance:
            relevance_str = self.convert_expression_to_string(not_clean(activity_node.relevance))
            if relevance_str and relevance_str != 'false':
                self.form_data["pages"][-1]["hide"] = {
                    "hideWhenExpression": f"{relevance_str}"
                }
        logger.debug(f"Started page: {page_label}")

    def start_section(self, group_node):
        """Start a new section for a group"""
        self.clean_sections()
        self.current_activity = group_node
        # Set process from id if not set
        default_label = f"Section {len(self.form_data['pages'][-1]['sections']) + 1}"
        if hasattr(group_node, 'root'):
            section_label = getattr(group_node.root, 'label', None)
        else:
            section_label = getattr(group_node, 'label', None)
        if section_label is None:
            label = getattr(group_node, 'label', None)
            if label is None:
                section_label = default_label
            else:
                section_label = label
        section_label = section_label.replace('\u00a0', ' ').strip()
        self.form_data['pages'][-1]['sections'].append({
            "label": section_label,
            "questions": []
        })

        if group_node.relevance:
            relevance_str = self.convert_expression_to_string(not_clean(group_node.relevance))
            if relevance_str and relevance_str != 'false':
                self.form_data["pages"][-1]['sections'][-1]["hide"] = {
                    "hideWhenExpression": f"{relevance_str}"
                }
        logger.debug(f"Started section: {section_label}")

    def create_calculation_page(self):
        """Create a dedicated page for all calculated fields"""
        if self.calculated_fields:
            self.clean_sections()
            self.clean_pages()
            page = {
                "label": "Calculations",
                "sections": [
                    {
                        "label": "Calculations",
                        "questions": self.calculated_fields
                    }
                ]
            }
            self.form_data["pages"].append(page)
            logger.debug("Created calculation page")

    def inject_version(self):
        # Add hidden version field using version() function
        question = {
            "id": "version",
            "type": "control",
            "label": "",
            "hide": {
                "hideWhenExpression": "true"
            },
            "questionOptions": {
                "calculate": {
                    "calculateExpression": "version()"
                }
            }
        }
        # Collect calculated fields to add to first section of each page
        self.calculated_fields.append(question)
