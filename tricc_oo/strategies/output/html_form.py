import logging
import os
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


class HTMLStrategy(BaseOutPutStrategy):
    processes = ["main"]
    project = None
    output_path = None

    def __init__(self, project, output_path):
        super().__init__(project, output_path)
        self.html_content = ""
        self.js_statements = []

    def get_tricc_operation_expression(self, operation):
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
        # Generate base HTML for nodes
        if hasattr(node, 'label') and node.label:
            self.html_content += f"<label for='{node.get_name()}'>{node.label}</label>\n"
        if hasattr(node, 'tricc_type'):
            onchange = "onchange='updateForm()'"
            if node.tricc_type == 'text':
                self.html_content += f"<input type='text' id='{node.get_name()}' name='{node.get_name()}' {onchange} />\n"  # noqa: E501
            elif node.tricc_type == 'integer':
                self.html_content += f"<input type='number' id='{node.get_name()}' name='{node.get_name()}' {onchange} />\n"  # noqa: E501
            # Add more types as needed
        return True

    def generate_relevance(self, node, **kwargs):
        # Generate JS for skip logic (relevance)
        if hasattr(node, 'expression') and node.expression:
            relevance_js = f"if ({self.convert_expression_to_js(node.expression)}) {{ document.getElementById('{node.get_name()}').style.display = 'block'; }} else {{ document.getElementById('{node.get_name()}').style.display = 'none'; }}"  # noqa: E501
            self.js_statements.append(relevance_js)
        return True

    def generate_calculate(self, node, **kwargs):
        # Generate JS for calculations
        if hasattr(node, 'expression') and node.expression:
            calc_js = f"document.getElementById('{node.get_name()}').value = {self.convert_expression_to_js(node.expression)};"  # noqa: E501
            self.js_statements.append(calc_js)
        return True

    def generate_export(self, node, **kwargs):
        # For OpenMRS, export is part of building HTML
        return True

    def export(self, start_pages, version):
        form_id = start_pages["main"].root.form_id or "openmrs_form"
        file_name = f"{form_id}.html"
        newpath = os.path.join(self.output_path, file_name)
        if not os.path.exists(self.output_path):
            os.makedirs(self.output_path)

        js_function = f"""
function updateForm() {{
    {"\n    ".join(self.js_statements)}
}}
window.onload = updateForm;
        """

        full_html = f"""
<!DOCTYPE html>
<html>
<head>
    <title>{start_pages["main"].root.label or 'OpenMRS Form'}</title>
</head>
<body>
    <form id="{form_id}">
        {self.html_content}
    </form>
    <script>
        {js_function}
    </script>
</body>
</html>
        """

        with open(newpath, 'w') as f:
            f.write(full_html)
        logger.info(f"Exported OpenMRS form to {newpath}")

    def get_tricc_operation_operand(self, r):
        if isinstance(r, TriccOperation):
            return self.get_tricc_operation_expression(r)
        elif isinstance(r, TriccReference):
            return f"document.getElementById('{get_export_name(r.value)}').value"
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
            return f"'{r.name}'"
        elif issubclass(r.__class__, TriccNodeInputModel):
            return f"document.getElementById('{get_export_name(r)}').value"
        elif issubclass(r.__class__, TriccNodeBaseModel):
            return f"document.getElementById('{get_export_name(r)}').value"
        else:
            raise NotImplementedError(f"This type of node {r.__class__} is not supported within an operation")

    def convert_expression_to_js(self, expression):
        if isinstance(expression, TriccOperation):
            return self.get_tricc_operation_expression(expression)
        else:
            return self.get_tricc_operation_operand(expression)

    # Implement operation methods as needed, similar to XLSForm but for JS
    def tricc_operation_equal(self, ref_expressions):
        return f"{ref_expressions[0]} === {ref_expressions[1]}"

    def tricc_operation_not_equal(self, ref_expressions):
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
            return " || ".join(ref_expressions)
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

    # Add more operations as needed...
