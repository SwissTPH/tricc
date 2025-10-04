import abc
import logging
import os
import json
import uuid
from tricc_oo.visitors.tricc import stashed_node_func, is_ready_to_process, process_reference, get_node_expressions
import datetime
from tricc_oo.strategies.output.base_output_strategy import BaseOutPutStrategy
from tricc_oo.models.base import (
    TriccOperator, not_clean,
    TriccOperation, TriccStatic, TriccReference, TriccNodeType
)
from tricc_oo.models.tricc import (
    TriccNodeSelectOption,
    TriccNodeInputModel,
    TriccNodeBaseModel,
)

from tricc_oo.models.calculate import TriccNodeDisplayCalculateBase
from tricc_oo.converters.tricc_to_xls_form import get_export_name

logger = logging.getLogger("default")

# Namespace for deterministic UUIDs
UUID_NAMESPACE = uuid.UUID('12345678-1234-5678-9abc-def012345678')


class OpenMRSStrategy(BaseOutPutStrategy):
    processes = ["main"]
    project = None
    output_path = None

    def __init__(self, project, output_path):
        super().__init__(project, output_path)
        form_id = getattr(self.project.start_pages["main"],'form_id', 'openmrs_form')
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
            "pages": [
                {
                    "label": "Main Page",
                    "sections": [
                        {
                            "label": "Main Section",
                            "questions": []
                        }
                    ]
                }
            ]
        }
        self.field_counter = 1
        self.questions_temp = []  # Temporary storage for questions with ordering info
        self.processing_order = 0  # Counter to track processing order

    def generate_id(self, name):
        return str(uuid.uuid5(UUID_NAMESPACE, name))

    def get_option_value(self, option_name):
        """Map option names to OpenMRS concept UUIDs"""
        if option_name.lower() == 'yes':
            return "1065AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA"
        elif option_name.lower() == 'no':
            return "1066AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA"
        else:
            return self.generate_id(option_name)

    def get_tricc_operation_expression(self, operation):
        # Similar to HTML, but for JSON, perhaps convert to string expressions
        ref_expressions = []
        if not hasattr(operation, "reference"):
            return self.get_tricc_operation_operand(operation)

        operator = getattr(operation, "operator", "")
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
        self.process_relevance(self.project.start_pages, pages=self.project.pages)

        logger.info("generate the calculate based on edges")
        self.process_calculate(self.project.start_pages, pages=self.project.pages)

        logger.info("finalize questions order")
        self.finalize_questions()

        logger.info("generate the export format")
        self.process_export(self.project.start_pages, pages=self.project.pages)

        logger.info("print the export")
        self.export(self.project.start_pages, version=version)

    def map_tricc_type_to_rendering(self, tricc_type):
        mapping = {
            'text': 'text',
            'integer': 'number',
            'select_one': 'select',
            'select_multiple': 'multiCheckbox'
        }
        return mapping.get(tricc_type, 'text')

    def generate_base(self, node, **kwargs):
        # Generate question for OpenMRS O3 schema
        # Handle activity nodes by processing their inner content
        if hasattr(node, 'tricc_type') and node.tricc_type == 'activity':
            # Process inner nodes of the activity
            if hasattr(node, 'nodes') and node.nodes:
                for inner_node in node.nodes.values():
                    self.generate_base(inner_node, **kwargs)
            return True

        processed_nodes = kwargs.get('processed_nodes', set())

        # Check if node is ready to be processed (similar to XLS form strategy)
        if not is_ready_to_process(node, processed_nodes, strict=False):
            return False

        # Process references to ensure dependencies are handled
        if not process_reference(node, processed_nodes, {}, replace_reference=False, codesystems=kwargs.get("codesystems", None)):
            return False

        if hasattr(node, 'tricc_type') and node.tricc_type in ['text', 'integer', 'select_one', 'select_multiple']:
            question = {
                "label": getattr(node, 'label', '').replace('\u00a0', ' ').strip(),
                "type": "obs",
                "questionOptions": {
                    "rendering": self.map_tricc_type_to_rendering(node.tricc_type),
                    "concept": "",  # Concept UUID, to be set
                },
                "required": str(getattr(node, 'required', False)),
                "unspecified": False,
                "id": get_export_name(node),
                "uuid": self.generate_id(get_export_name(node))
            }
            if node.tricc_type in ['select_one', 'select_multiple']:
                # Add answers if options
                if hasattr(node, 'options'):
                    answers = []
                    for opt in node.options.values():
                        display = getattr(opt, 'label', opt.name)
                        # All options now use UUIDs
                        concept_val = self.get_option_value(display)
                        answers.append({
                            "label": display,
                            "concept": concept_val,
                            "conceptMappings": []
                        })
                    question["questionOptions"]["answers"] = answers
                else:
                    question["questionOptions"]["answers"] = []
            # Set concept for the question itself if it's a coded question
            if node.tricc_type in ['select_one', 'select_multiple']:
                # Use the question's export name as concept
                question["questionOptions"]["concept"] = self.generate_id(get_export_name(node))

            # Store question with processing order
            self.questions_temp.append({
                'question': question,
                'processing_order': self.processing_order,
                'node_id': getattr(node, 'id', '')
            })
            self.processing_order += 1
            self.field_counter += 1
        return True

    def generate_relevance(self, node, processed_nodes, **kwargs):
        # Check if node is ready to be processed (similar to XLS form strategy)
        if not is_ready_to_process(node, processed_nodes, strict=False):
            return False

        # Process references to ensure dependencies are handled
        if not process_reference(node, processed_nodes, {}, replace_reference=False, codesystems=kwargs.get("codesystems", None)):
            return False
        
        # For relevance, set hide at question level
        relevance = None
        if hasattr(node, 'relevance') and node.relevance:
            relevance = node.relevance
        if hasattr(node, 'expression') and node.expression:
            relevance = node.expression
        if relevance:
            question_id = get_export_name(node)
            for item in self.questions_temp:
                if item['question']["id"] == question_id:
                    # hide is the opposite of relevance, so use negate
                    relevance_str = self.convert_expression_to_string(not_clean(relevance))
                    if relevance_str and relevance_str != 'false':
                        item['question']["hide"] = {
                            "hideWhenExpression": f"{relevance_str}"
                        }
                    break
        return True

    def generate_calculate(self, node, processed_nodes, **kwargs):
        # For calculations, set calculate in questionOptions
        # Check if node is ready to be processed (similar to XLS form strategy)
        if not is_ready_to_process(node, processed_nodes, strict=True):
            return False

        # Process references to ensure dependencies are handled
        if not process_reference(node, processed_nodes, {}, replace_reference=True, codesystems=kwargs.get("codesystems", None)):
            return False
        
        if issubclass(node.__class__, TriccNodeDisplayCalculateBase):
            expression = None
            if hasattr(node, 'expression') and node.expression:
                expression = node.expression
            elif hasattr(node, 'expression_reference') and node.expression_reference:
                expression = node.expression_reference
            elif node.prev_nodes:
                expression = get_node_expressions(node, processed_nodes=processed_nodes, process=kwargs.get("process", None))

                
            
            if expression:
                question_id = get_export_name(node)
                found = False
                for item in self.questions_temp:
                    if item['question']["id"] == question_id:
                        item['question']["questionOptions"]["calculate"] = {
                            "calculateExpression": self.convert_expression_to_string(expression)
                        }
                        found = True
                        break
                if not found:
                    question = {
                    "id": get_export_name(node),
                    "label": getattr(node, 'label', '').replace('\u00a0', ' ').strip(),
                    "isHidden": True,
                    "questionOptions":{
                        "calculate":{
                            "calculateExpression":self.convert_expression_to_string(expression)
                            }
                        }
                    }
                    self.questions_temp.append({
                        'question': question,
                        'processing_order': self.processing_order,
                        'node_id': getattr(node, 'id', '')
                    })
        return True

    def finalize_questions(self):
        """Sort questions by processing order and add them to the form in correct order"""
        # Sort by processing_order to maintain the order nodes were processed
        sorted_questions = sorted(self.questions_temp, key=lambda x: x['processing_order'])
        # Add sorted questions to the form
        for item in sorted_questions:
            self.form_data["pages"][0]["sections"][0]["questions"].append(item['question'])
        # Clear temporary storage
        self.questions_temp = []

    def generate_export(self, node, **kwargs):
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
            return get_export_name(r.value)
        elif isinstance(r, TriccStatic):
            if isinstance(r.value, bool):
                return str(r.value).lower()
            if isinstance(r.value, str):
                return f"'{r.value}'"
            else:
                return str(r.value)
        elif isinstance(r, str):
            return f"{r}"
        elif isinstance(r, (int, float)):
            return str(r)
        elif isinstance(r, TriccNodeSelectOption):
            return f"'{self.get_option_value(r.name)}'"
        elif issubclass(r.__class__, TriccNodeInputModel):
            return get_export_name(r)
        elif issubclass(r.__class__, TriccNodeBaseModel):
            return get_export_name(r)
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
        return f"{ref_expressions[0]} == {ref_expressions[1]}"

    def tricc_operation_not_equal(self, ref_expressions):
        return f"{ref_expressions[0]} != {ref_expressions[1]}"

    def tricc_operation_and(self, ref_expressions):
        if len(ref_expressions) == 1:
            return ref_expressions[0]
        if len(ref_expressions) > 1:
            return " and ".join(ref_expressions)
        else:
            return "true"

    def tricc_operation_or(self, ref_expressions):
        if len(ref_expressions) == 1:
            return ref_expressions[0]
        if len(ref_expressions) > 1:
            return " or ".join(ref_expressions)
        else:
            return "true"

    def tricc_operation_not(self, ref_expressions):
        return f"!({ref_expressions[0]})"

    def tricc_operation_plus(self, ref_expressions):
        return " + ".join(ref_expressions)

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
        return f"arrayContains({ref_expressions[0]}, {ref_expressions[1]})"

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
        return f"{ref_expressions[0]} == true"

    def tricc_operation_isfalse(self, ref_expressions):
        return f"{ref_expressions[0]} == false"

    def tricc_operation_parenthesis(self, ref_expressions):
        return f"({ref_expressions[0]})"

    def tricc_operation_between(self, ref_expressions):
        return f"{ref_expressions[0]} >= {ref_expressions[1]} and {ref_expressions[0]} < {ref_expressions[2]}"

    def tricc_operation_isnull(self, ref_expressions):
        return f"isEmpty({ref_expressions[0]})"

    def tricc_operation_isnotnull(self, ref_expressions):
        return f"{ref_expressions[0]} != ''"

    def tricc_operation_isnottrue(self, ref_expressions):
        return f"{ref_expressions[0]} != true"

    def tricc_operation_isnotfalse(self, ref_expressions):
        return f"{ref_expressions[0]} != false"

    def tricc_operation_notexist(self, ref_expressions):
        return f"{ref_expressions[0]} == ''"

    def tricc_operation_case(self, ref_expressions):
        # Simplified, assuming list of conditions
        parts = []
        for i in range(0, len(ref_expressions), 2):
            if i + 1 < len(ref_expressions):
                parts.append(f"if({ref_expressions[i]}, {ref_expressions[i+1]})")
        return " or ".join(parts)  # Simplified

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
            parts.append(f"{ref} != ''")
        return " and ".join(parts)

    def tricc_operation_cast_number(self, ref_expressions):
        return f"number({ref_expressions[0]})"

    def tricc_operation_cast_integer(self, ref_expressions):
        return f"int({ref_expressions[0]})"

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

    # Add more operations as needed...
