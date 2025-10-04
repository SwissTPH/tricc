import logging
import os
import json
import datetime
from tricc_oo.strategies.output.base_output_strategy import BaseOutPutStrategy
from tricc_oo.models.base import (
    TriccOperation,
    TriccStatic, TriccReference
)
from tricc_oo.models.tricc import (
    TriccNodeSelectOption,
    TriccNodeInputModel,
    TriccNodeBaseModel
)
from tricc_oo.converters.tricc_to_xls_form import get_export_name

logger = logging.getLogger("default")


class FHIRStrategy(BaseOutPutStrategy):
    processes = ["main"]
    project = None
    output_path = None

    def __init__(self, project, output_path):
        super().__init__(project, output_path)
        self.questionnaires = {}  # segment -> questionnaire
        self.cql_libraries = {}
        self.fml_mappings = {}

    def get_tricc_operation_expression(self, operation):
        # For CQL
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

        logger.info("generate the export format")
        self.process_export(self.project.start_pages, pages=self.project.pages)

        logger.info("print the export")
        self.export(self.project.start_pages, version=version)

    def generate_base(self, node, **kwargs):
        # Generate Questionnaire items per segment
        segment = getattr(node, 'segment', 'main')
        if segment not in self.questionnaires:
            self.questionnaires[segment] = {
                "resourceType": "Questionnaire",
                "id": f"questionnaire-{segment}",
                "url": f"http://example.com/Questionnaire/{segment}",
                "status": "draft",
                "item": []
            }
        item = {
            "linkId": get_export_name(node),
            "text": getattr(node, 'label', ''),
            "type": self.map_tricc_type_to_fhir(node.tricc_type if hasattr(node, 'tricc_type') else 'text')
        }
        if hasattr(node, 'options') and node.options:
            item["answerOption"] = [{"valueString": opt.name} for opt in node.options]
        self.questionnaires[segment]["item"].append(item)
        return True

    def generate_relevance(self, node, **kwargs):
        # Add enableWhen to Questionnaire item with FHIRPath
        if hasattr(node, 'expression') and node.expression:
            segment = getattr(node, 'segment', 'main')
            if segment in self.questionnaires:
                for item in self.questionnaires[segment]["item"]:
                    if item["linkId"] == get_export_name(node):
                        # Use FHIRPath expression
                        fhirpath_expr = self.convert_expression_to_fhirpath(node.expression)
                        item["enableWhen"] = [{
                            "question": self.get_question_link(node.expression),
                            "operator": "=",
                            "answerString": self.get_answer_value(node.expression)
                        }]
                        # Alternatively, use expression for complex logic
                        item["enableWhenExpression"] = {
                            "language": "text/fhirpath",
                            "expression": fhirpath_expr
                        }
                        break
        return True

    def generate_calculate(self, node, **kwargs):
        # Add calculatedExpression to Questionnaire item with FHIRPath
        if hasattr(node, 'expression') and node.expression:
            segment = getattr(node, 'segment', 'main')
            if segment in self.questionnaires:
                for item in self.questionnaires[segment]["item"]:
                    if item["linkId"] == get_export_name(node):
                        fhirpath_expr = self.convert_expression_to_fhirpath(node.expression)
                        item["calculatedExpression"] = {
                            "language": "text/fhirpath",
                            "expression": fhirpath_expr
                        }
                        break
            # Still add to CQL for population if needed
            if segment not in self.cql_libraries:
                self.cql_libraries[segment] = f"library {segment}Library version '1.0.0'\n\n"
            cql_expr = self.convert_expression_to_cql(node.expression)
            self.cql_libraries[segment] += f"define {get_export_name(node)}: {cql_expr}\n"
        return True

    def generate_export(self, node, **kwargs):
        # Generate FML for saving based on content_type
        content_type = getattr(node, 'content_type', 'Observation')
        if content_type not in self.fml_mappings:
            self.fml_mappings[content_type] = f"map \"{content_type}\" {{\n"
        # Add mapping rules
        self.fml_mappings[content_type] += f"  {get_export_name(node)} -> {content_type}.{get_export_name(node)}\n"
        return True

    def export(self, start_pages, version):
        form_id = start_pages["main"].root.form_id or "fhir_form"
        base_path = os.path.join(self.output_path, form_id)
        if not os.path.exists(base_path):
            os.makedirs(base_path)

        # Export Questionnaires
        for segment, q in self.questionnaires.items():
            file_name = f"{segment}.json"
            path = os.path.join(base_path, file_name)
            with open(path, 'w') as f:
                json.dump(q, f, indent=2)

        # Export CQL
        for segment, cql in self.cql_libraries.items():
            file_name = f"{segment}.cql"
            path = os.path.join(base_path, file_name)
            with open(path, 'w') as f:
                f.write(cql)

        # Export FML
        for content_type, fml in self.fml_mappings.items():
            fml += "}\n"
            file_name = f"{content_type}.map"
            path = os.path.join(base_path, file_name)
            with open(path, 'w') as f:
                f.write(fml)

        logger.info(f"Exported FHIR resources to {base_path}")

    def map_tricc_type_to_fhir(self, tricc_type):
        mapping = {
            'text': 'string',
            'integer': 'integer',
            'decimal': 'decimal',
            'select_one': 'choice',
            'select_multiple': 'choice',
            'date': 'date',
            'time': 'time',
            'datetime': 'dateTime',
            'boolean': 'boolean'
        }
        return mapping.get(tricc_type, 'string')

    def get_question_link(self, expression):
        # Simplified, assume first reference
        if isinstance(expression, TriccOperation) and hasattr(expression, 'reference'):
            for r in expression.reference:
                if isinstance(r, TriccReference):
                    return get_export_name(r.value)
        return ""

    def get_answer_value(self, expression):
        # Simplified
        return "true"

    def get_tricc_operation_operand(self, r):
        if isinstance(r, TriccOperation):
            return self.get_tricc_operation_expression(r)
        elif isinstance(r, TriccReference):
            return get_export_name(r.value)
        elif isinstance(r, TriccStatic):
            if isinstance(r.value, str):
                return f"'{r.value}'"
            else:
                return str(r.value)
        elif isinstance(r, str):
            return f"'{r}'"
        elif isinstance(r, (int, float)):
            return str(r)
        elif isinstance(r, TriccNodeSelectOption):
            return f"'{r.name}'"
        elif issubclass(r.__class__, TriccNodeInputModel):
            return get_export_name(r)
        elif issubclass(r.__class__, TriccNodeBaseModel):
            return get_export_name(r)
        else:
            raise NotImplementedError(f"This type of node {r.__class__} is not supported within an operation")

    def convert_expression_to_cql(self, expression):
        if isinstance(expression, TriccOperation):
            return self.get_tricc_operation_expression(expression)
        else:
            return self.get_tricc_operation_operand(expression)

    def convert_expression_to_fhirpath(self, expression):
        # For FHIRPath, similar to CQL but in FHIR context
        # For questionnaire, references to other questions
        if isinstance(expression, TriccOperation):
            return self.get_tricc_operation_expression_fhirpath(expression)
        else:
            return self.get_tricc_operation_operand_fhirpath(expression)

    def get_tricc_operation_expression_fhirpath(self, operation):
        ref_expressions = []
        if not hasattr(operation, "reference"):
            return self.get_tricc_operation_operand_fhirpath(operation)
        for r in operation.reference:
            if isinstance(r, list):
                r_expr = [
                    (
                        self.get_tricc_operation_expression_fhirpath(sr)
                        if isinstance(sr, TriccOperation)
                        else self.get_tricc_operation_operand_fhirpath(sr)
                    )
                    for sr in r
                ]
            elif isinstance(r, TriccOperation):
                r_expr = self.get_tricc_operation_expression_fhirpath(r)
            else:
                r_expr = self.get_tricc_operation_operand_fhirpath(r)
            if isinstance(r_expr, TriccReference):
                r_expr = self.get_tricc_operation_operand_fhirpath(r_expr)
            ref_expressions.append(r_expr)

        if hasattr(self, f"tricc_operation_fhirpath_{operation.operator}"):
            callable = getattr(self, f"tricc_operation_fhirpath_{operation.operator}")
            return callable(ref_expressions)
        else:
            # Fallback to CQL operations
            if hasattr(self, f"tricc_operation_{operation.operator}"):
                callable = getattr(self, f"tricc_operation_{operation.operator}")
                return callable(ref_expressions)
            else:
                raise NotImplementedError(
                    f"This type of operation '{operation.operator}' is not supported"
                )

    def get_tricc_operation_operand_fhirpath(self, r):
        if isinstance(r, TriccOperation):
            return self.get_tricc_operation_expression_fhirpath(r)
        elif isinstance(r, TriccReference):
            # In FHIRPath, reference to another question's answer
            return f"%questionnaire.item.where(linkId='{get_export_name(r.value)}').answer.value"
        elif isinstance(r, TriccStatic):
            if isinstance(r.value, str):
                return f"'{r.value}'"
            else:
                return str(r.value)
        elif isinstance(r, str):
            return f"'{r}'"
        elif isinstance(r, (int, float)):
            return str(r)
        elif isinstance(r, TriccNodeSelectOption):
            return f"'{r.name}'"
        elif issubclass(r.__class__, TriccNodeInputModel):
            return f"%questionnaire.item.where(linkId='{get_export_name(r)}').answer.value"
        elif issubclass(r.__class__, TriccNodeBaseModel):
            return f"%questionnaire.item.where(linkId='{get_export_name(r)}').answer.value"
        else:
            raise NotImplementedError(f"This type of node {r.__class__} is not supported within an operation")

    # FHIRPath operations, same as CQL for now
    def tricc_operation_fhirpath_equal(self, ref_expressions):
        return f"{ref_expressions[0]} = {ref_expressions[1]}"

    def tricc_operation_fhirpath_not_equal(self, ref_expressions):
        return f"{ref_expressions[0]} != {ref_expressions[1]}"

    def tricc_operation_fhirpath_and(self, ref_expressions):
        return " and ".join(ref_expressions)

    def tricc_operation_fhirpath_or(self, ref_expressions):
        return " or ".join(ref_expressions)

    def tricc_operation_fhirpath_not(self, ref_expressions):
        return f"not {ref_expressions[0]}"

    def tricc_operation_fhirpath_plus(self, ref_expressions):
        return " + ".join(ref_expressions)

    def tricc_operation_fhirpath_minus(self, ref_expressions):
        if len(ref_expressions) > 1:
            return " - ".join(ref_expressions)
        return f"-{ref_expressions[0]}"

    def tricc_operation_fhirpath_more(self, ref_expressions):
        return f"{ref_expressions[0]} > {ref_expressions[1]}"

    def tricc_operation_fhirpath_less(self, ref_expressions):
        return f"{ref_expressions[0]} < {ref_expressions[1]}"

    def tricc_operation_fhirpath_more_or_equal(self, ref_expressions):
        return f"{ref_expressions[0]} >= {ref_expressions[1]}"

    def tricc_operation_fhirpath_less_or_equal(self, ref_expressions):
        return f"{ref_expressions[0]} <= {ref_expressions[1]}"

    # Operation methods for CQL
    def tricc_operation_equal(self, ref_expressions):
        return f"{ref_expressions[0]} = {ref_expressions[1]}"

    def tricc_operation_not_equal(self, ref_expressions):
        return f"{ref_expressions[0]} != {ref_expressions[1]}"

    def tricc_operation_and(self, ref_expressions):
        return " and ".join(ref_expressions)

    def tricc_operation_or(self, ref_expressions):
        return " or ".join(ref_expressions)

    def tricc_operation_not(self, ref_expressions):
        return f"not {ref_expressions[0]}"

    def tricc_operation_plus(self, ref_expressions):
        return " + ".join(ref_expressions)

    def tricc_operation_minus(self, ref_expressions):
        if len(ref_expressions) > 1:
            return " - ".join(ref_expressions)
        return f"-{ref_expressions[0]}"

    def tricc_operation_more(self, ref_expressions):
        return f"{ref_expressions[0]} > {ref_expressions[1]}"

    def tricc_operation_less(self, ref_expressions):
        return f"{ref_expressions[0]} < {ref_expressions[1]}"

    def tricc_operation_more_or_equal(self, ref_expressions):
        return f"{ref_expressions[0]} >= {ref_expressions[1]}"

    def tricc_operation_less_or_equal(self, ref_expressions):
        return f"{ref_expressions[0]} <= {ref_expressions[1]}"
