import logging
import os
import json
import uuid
import string
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
    TriccNodeDisplayModel,
    TriccNodeCalculateBase,
    TriccNodeActivity,
)
from tricc_oo.models.calculate import TriccNodeDisplayCalculateBase
from tricc_oo.models.ordered_set import OrderedSet

logger = logging.getLogger("default")

# Namespace for deterministic UUIDs
UUID_NAMESPACE = uuid.UUID('87654321-4321-8765-cba9-fed098765432')


class DHIS2Strategy(BaseOutPutStrategy):
    processes = ["main"]
    project = None
    output_path = None

    def __init__(self, project, output_path):
        super().__init__(project, output_path)
        form_id = getattr(self.project.start_pages["main"], 'form_id', 'dhis2_program')
        self.program_metadata = {
            "id": self.generate_id(form_id),
            "name": form_id,
            "shortName": form_id[:50],  # DHIS2 shortName limit
            "programType": "WITHOUT_REGISTRATION",
            "programStages": [],
            "programRules": []
        }
        self.option_sets = {}
        self.options = {}
        self.data_elements = {}
        self.program_rules = []
        self.program_rule_actions = []
        self.program_rule_variables = []
        self.field_counter = 1
        self.current_section = None
        self.concept_map = {}
        # Track programRuleActions per stage
        self.stage_rule_actions = {}
        self.sections = {}

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
            return get_export_name(r)

    def generate_id(self, name):
        """Generate DHIS2-compliant UID: 1 letter + 10 alphanumeric characters"""
        # Convert UUID to base62-like string and take first 11 chars, ensuring starts with letter
        # Create DHIS2 UID: start with letter, followed by 10 alphanum chars
        letters = string.ascii_letters
        alphanum = string.ascii_letters + string.digits

        # Use hash of the name to get deterministic but varied results
        import hashlib
        hash_obj = hashlib.md5(name.encode('utf-8')).digest()
        hash_int = int.from_bytes(hash_obj, byteorder='big')

        # First character: letter
        first_char = letters[hash_int % len(letters)]

        # Remaining 10 characters: alphanumeric
        remaining_chars = ''
        for i in range(10):
            remaining_chars += alphanum[(hash_int >> (i * 6)) % len(alphanum)]

        return first_char + remaining_chars

    def get_option_value(self, option_name):
        if option_name == 'true':
            return TriccStatic(True)
        elif option_name == 'false':
            return TriccStatic(False)
        return self.concept_map.get(option_name, option_name)

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
            elif isinstance(r_expr, TriccStatic) and isinstance(r_expr.value, bool):
                r_expr = str(r_expr.value).lower()
            ref_expressions.append(r_expr)

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

    def map_tricc_type_to_dhis2_value_type(self, node):
        mapping = {
            'text': 'TEXT',
            'integer': 'INTEGER',
            'decimal': 'NUMBER',
            'date': 'DATE',
            'datetime': 'DATETIME',
            'select_one': 'TEXT',  # DHIS2 handles options via optionSets
            'select_multiple': 'TEXT',  # Multiple selections as comma-separated
            'select_yesno': 'BOOLEAN',
            'yesno': 'BOOLEAN',
            'boolean': 'BOOLEAN',
            'not_available': 'BOOLEAN',
            'note': 'LONG_TEXT'
        }
        return mapping.get(node.tricc_type, 'TEXT')

    def generate_base(self, node, processed_nodes, **kwargs):
        if generate_base(node, processed_nodes, **kwargs):
            if getattr(node, 'name', '') not in ('true', 'false'):
                self.concept_map[node.name] = self.generate_id(self.get_export_name(node))
            return True
        return False

    def generate_relevance(self, node, processed_nodes, **kwargs):
        if not is_ready_to_process(node, processed_nodes, strict=True):
            return False

        if node not in processed_nodes:
            relevance = None
            if hasattr(node, 'relevance') and node.relevance:
                relevance = node.relevance
            if hasattr(node, 'expression') and node.expression:
                relevance = node.expression
            if relevance:
                relevance_str = self.convert_expression_to_string(not_clean(relevance))
                if relevance_str and relevance_str != 'false':
                    # Create program rule action for hiding/showing based on relevance
                    rule_id = self.generate_id(f"rule_{node.get_name()}_relevance")
                    action_id = self.generate_id(f"action_{rule_id}")

                    if isinstance(node, TriccNodeActivity):
                        # For activities, use HIDESECTION action instead of HIDEFIELD
                        # Store activity reference for later section ID assignment
                        program_rule_action = {
                            "id": action_id,
                            "programRuleActionType": "HIDESECTION",
                            "activity_ref": node,  # Temporary reference to be replaced with section ID
                            "programRule": {"id": rule_id},
                        }
                    else:
                        # For regular nodes, use HIDEFIELD action
                        program_rule_action = {
                            "id": action_id,
                            "programRuleActionType": "HIDEFIELD",
                            "dataElement": {
                                "id": self.generate_id(self.get_export_name(node))
                            },
                            "programRule": {"id": rule_id}
                        }
                    self.program_rule_actions.append(program_rule_action)

                    # Create program rule referencing the action
                    self.program_rules.append({
                        "id": rule_id,
                        "name": f"Hide {node.get_name()} when condition met",
                        "description": f"Hide {node.get_name()} based on relevance",
                        "condition": f"!({relevance_str})",  # Negate for hide when true
                        "programRuleActions": [{"id": action_id}]
                    })
        return True

    def generate_data_element(self, node):
        if issubclass(node.__class__, TriccNodeDisplayModel) and not isinstance(node, TriccNodeSelectOption):
            de_id = self.generate_id(self.get_export_name(node))

            # Check if this is a boolean question (yes/no with boolean options)
            is_boolean_question = False
            if hasattr(node, 'options') and node.options:
                option_names = [
                    str(self.get_export_name(opt)).lower()
                    for opt in node.options.values()
                    if isinstance(opt, TriccNodeSelectOption)]
                # If options are only true/false or yes/no variants, treat as boolean
                boolean_options = {'true', 'false', 'yes', 'no', '1', '0'}
                if all(opt in boolean_options for opt in option_names):
                    is_boolean_question = True

            # Override valueType for boolean questions
            value_type = self.map_tricc_type_to_dhis2_value_type(node)
            if is_boolean_question:
                value_type = "BOOLEAN"

            data_element = {
                "id": de_id,
                "name": self.get_export_name(node),
                "shortName": node.name[:50],
                "displayFormName": getattr(node, 'label', node.name).replace('\u00a0', ' ').strip(),
                "valueType": value_type,
                "domainType": "TRACKER",
                "aggregationType": "NONE"
            }

            # Only create optionSet for non-boolean select questions
            if node.tricc_type in ['select_one', 'select_multiple'] and not is_boolean_question:
                # Create optionSet for choices
                if hasattr(node, 'options') and node.options:
                    option_set_id = self.generate_id(f"optionset_{node.name}")
                    data_element["optionSet"] = {"id": option_set_id}

                    # Create the actual optionSet definition
                    option_set = {
                        "id": option_set_id,
                        "name": f"{node.name} Options",
                        "shortName": f"{node.name}_opts"[:50],
                        "valueType": "TEXT",
                        "options": []
                    }

                    # Add options (node.options is a dict, not a list)
                    for key, option in node.options.items():
                        if isinstance(option, TriccNodeSelectOption):
                            option_id = self.generate_id(f"option_{node.name}_{option.name}")
                            option_name = self.get_export_name(option)
                            if isinstance(option_name, str):
                                option_name = option_name.replace('\u00a0', ' ').strip()
                            elif isinstance(option_name, TriccStatic):
                                option_name = str(option_name.value)
                            # Create separate option entity
                            option_def = {
                                "id": option_id,
                                "name": option_name,
                                "shortName": option.name[:50],
                                "code": str(self.get_export_name(option))
                            }
                            self.options[option_id] = option_def

                            # Add option reference to optionSet (only ID)
                            option_set["options"].append({"id": option_id})

                    self.option_sets[option_set_id] = option_set

            self.data_elements[node.name] = data_element
            return data_element
        return None

    def generate_calculate(self, node, processed_nodes, **kwargs):
        if generate_calculate(node, processed_nodes, **kwargs):
            if issubclass(node.__class__, TriccNodeCalculateBase) and node.expression:
                # Create program rule variable for the calculate
                var_id = self.generate_id(self.get_export_name(node))
                expression_str = self.convert_expression_to_string(node.expression)

                # Determine data type from operation
                data_type = "TEXT"  # default
                if hasattr(node.expression, 'get_datatype'):
                    operation_datatype = node.expression.get_datatype()
                    if operation_datatype:
                        # Create a mock node with the datatype to use the mapping function
                        class MockNode:
                            def __init__(self, tricc_type):
                                self.tricc_type = tricc_type
                        mock_node = MockNode(operation_datatype)
                        data_type = self.map_tricc_type_to_dhis2_value_type(mock_node)

                program_rule_variable = {
                    "id": var_id,
                    "name": self.get_export_name(node.name)[:50],
                    "programRuleVariableSourceType": "CALCULATED_VALUE",
                    "calculatedValueScript": expression_str,
                    "dataType": data_type,
                    "useCodeForOptionSet": False,
                    "program": {"id": self.program_metadata["id"]}
                }
                self.program_rule_variables.append(program_rule_variable)
                # Add to concept map for potential referencing
                self.concept_map[node.name] = var_id
            return True
        return False

    def process_export(self, start_pages, **kwargs):
        self.activity_export(start_pages["main"], **kwargs)

    def activity_export(self, activity, processed_nodes=None, **kwargs):
        if processed_nodes is None:
            processed_nodes = OrderedSet()
        stashed_nodes = OrderedSet()
        groups = {}
        groups[activity.id] = 0
        path_len = 0
        process = ["main"]

        # Create program stage
        stage_id = self.generate_id(self.get_export_name(activity))
        program_stage = {
            "id": stage_id,
            "name": getattr(activity.root, 'label', 'Main Stage').replace('\u00a0', ' ').strip(),
            "programStageDataElements": [],
            "programStageSections": []
        }
        self.program_metadata["programStages"].append(program_stage)

        # Start with the main section for this activity
        self.start_section(activity, groups, processed_nodes, process, **kwargs)

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

        # End the main section
        self.end_section(activity, groups, **kwargs)

        # Manage stashed nodes similar to other strategies
        prev_stashed_nodes = stashed_nodes.copy()
        loop_count = 0
        len_prev_processed_nodes = 0
        while len(stashed_nodes) > 0:
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
                if s_node.group is None:
                    logger.critical("ERROR group is none for node {}".format(s_node.get_name()))

                # Start section for stashed node if it's a different group
                self.start_section(s_node.group, groups, processed_nodes, process, relevance=True, **kwargs)

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

                # End section for stashed node
                self.end_section(s_node.group, groups, **kwargs)

        return processed_nodes

    def start_section(self, cur_group, groups, processed_nodes, process, relevance=False, **kwargs):
        name = get_export_name(cur_group)

        if name in groups:
            groups[name] += 1
            name = name + "_" + str(groups[name])
        else:
            groups[name] = 0

        relevance_expression = (
            cur_group.relevance if (
                relevance and
                cur_group.relevance is not None and
                cur_group.relevance != ""
            ) else ""
        )

        if not relevance:
            relevance_expression = ""
        elif isinstance(relevance_expression, (TriccOperation, TriccStatic)):
            relevance_expression = self.get_tricc_operation_expression(relevance_expression)

        # Create section
        section_id = self.generate_id(f"section_{name}")
        section_name = name
        if cur_group and hasattr(cur_group, 'label') and cur_group.label:
            section_name = cur_group.label.replace('\u00a0', ' ').strip()
        section = {
            "id": section_id,
            "name": section_name,
            "sortOrder": len(self.sections),
            "programStage": {"id": self.program_metadata["programStages"][-1]["id"]},
            "dataElements": [],
            "activity_ref": cur_group
        }
        # Add section to program stage
        if self.program_metadata["programStages"]:
            self.program_metadata["programStages"][-1]["programStageSections"].append({"id": section_id})

        self.sections[section_id] = section
        self.current_section = section_id

    def end_section(self, cur_group, groups, **kwargs):
        # In DHIS2, sections don't have explicit end markers like XLSForm groups
        # The section is already created and added to the program stage
        pass

    def generate_export(self, node, processed_nodes, **kwargs):
        if not is_ready_to_process(node, processed_nodes, strict=True):
            return False

        if not process_reference(
            node, processed_nodes, {}, replace_reference=False, codesystems=kwargs.get("codesystems", None)
        ):
            return False

        if node not in processed_nodes:
            # Skip creating data elements for calculate nodes - they should only be program rule variables
            if not issubclass(node.__class__, TriccNodeCalculateBase):
                data_element = self.generate_data_element(node)
                if data_element:
                    # Add to program stage
                    if self.program_metadata["programStages"]:
                        psde_id = self.generate_id(f"psde_{node.name}")
                        psde = {
                            "id": psde_id,
                            "dataElement": {"id": data_element["id"]},
                            "compulsory": bool(getattr(node, 'required', False))
                        }
                        self.program_metadata["programStages"][-1]["programStageDataElements"].append(psde)

                        # Add data element to current section
                        if self.current_section and self.current_section in self.sections:
                            self.sections[self.current_section]["dataElements"].append({"id": data_element["id"]})

        return True

    def clean_section(self, program_stages_payload):
        """Clean sections by removing empty ones and merging sections with same activity_ref"""
        sections_to_remove = set()
        prev_activity_ref = None
        prev_section_id = None

        for section in sorted(self.sections.values(), key=lambda x: x["sortOrder"]):
            section_id = section["id"]
            activity_ref = section.get("activity_ref")
            # Remove empty sections
            if not section.get("dataElements"):
                sections_to_remove.add(section_id)

            # Check for sections with same activity_ref
            elif activity_ref == prev_activity_ref:
                # Merge this section into the existing one
                existing_section = self.sections[prev_section_id]

                # Move data elements to existing section
                existing_section["dataElements"].extend(section["dataElements"])

                # Mark this section for removal
                sections_to_remove.add(section_id)
            else:
                prev_activity_ref = activity_ref
                prev_section_id = section_id

        # Remove sections that should be removed
        for section_id in sections_to_remove:
            if section_id in self.sections:
                del self.sections[section_id]

        # Update stage sections to remove deleted sections
        for stage in program_stages_payload:
            stage["programStageSections"][:] = [
                s for s in stage["programStageSections"]
                if s["id"] not in sections_to_remove
            ]

    def export(self, start_pages, version):
        form_id = start_pages["main"].root.form_id or "dhis2_program"
        base_path = os.path.join(self.output_path, form_id)
        if not os.path.exists(base_path):
            os.makedirs(base_path)

        # Prepare collections for all entities
        program_rules_payload = []
        program_rule_actions_payload = []
        program_stages_payload = []
        program_rule_variables_payload = []

        if self.program_metadata["programStages"]:
            # Extract full stage definitions
            program_stages_payload = [
                {
                    **stage,
                    "program": {"id": self.program_metadata["id"]}
                }
                for stage in self.program_metadata["programStages"]
            ]
            # Clean sections before processing actions to ensure only valid sections are used
            self.clean_section(program_stages_payload)
            # In program, only keep stage ID references
            self.program_metadata["programStages"] = [
                {"id": stage["id"]}
                for stage in program_stages_payload
            ]
        else:
            program_stages_payload = []

        if self.program_rule_actions:
            # Resolve activity references to section IDs for HIDESECTION actions
            program_rule_actions_payload = []
            for action in self.program_rule_actions:
                if action.get("activity_ref"):
                    # Find all sections for this activity (after cleaning)
                    activity = action["activity_ref"]
                    matching_sections = [
                        sec_id for sec_id, section in self.sections.items()
                        if section.get("activity_ref") == activity
                    ]

                    # Create one action per matching section
                    for i, section_id in enumerate(matching_sections):
                        action_copy = dict(action)
                        action_copy["programStageSection"] = {"id": section_id}
                        del action_copy["activity_ref"]

                        if i > 0:
                            # For additional sections, create new IDs for action and corresponding rule
                            original_rule_id = action["programRule"]["id"]
                            new_rule_id = self.generate_id(f"{original_rule_id}_section_{i}")
                            new_action_id = self.generate_id(f"{action['id']}_section_{i}")

                            action_copy["id"] = new_action_id
                            action_copy["programRule"] = {"id": new_rule_id}

                            # Create duplicate rule with new ID
                            original_rule = next(
                                (r for r in self.program_rules if r["id"] == original_rule_id), None
                            )
                            if original_rule:
                                new_rule = dict(original_rule)
                                new_rule["id"] = new_rule_id
                                new_rule["name"] = f"{original_rule['name']} (Section {i})"
                                new_rule["programRuleActions"] = [{"id": new_action_id}]
                                self.program_rules.append(new_rule)

                        program_rule_actions_payload.append(action_copy)
                else:
                    # Non-activity actions (HIDEFIELD) can be added directly
                    program_rule_actions_payload.append(action)

        if self.program_rules:
            program_rules_payload = [
                {
                    **rule,
                    "program": {"id": self.program_metadata["id"]}
                }
                for rule in self.program_rules
            ]

        if self.program_rule_variables:
            program_rule_variables_payload = self.program_rule_variables

        # Build the program with references to other entities
        program_payload = dict(self.program_metadata)
        if program_rule_variables_payload:
            program_payload["programRuleVariables"] = [
                {"id": var["id"]}
                for var in program_rule_variables_payload
            ]
        if program_rules_payload:
            program_payload["programRules"] = [
                {"id": rule["id"]}
                for rule in program_rules_payload
            ]

        # Create single comprehensive payload with all entities at root level
        full_payload = {
            "programs": [program_payload]
        }

        if program_stages_payload:
            full_payload["programStages"] = program_stages_payload
        if program_rules_payload:
            full_payload["programRules"] = program_rules_payload
        if program_rule_actions_payload:
            full_payload["programRuleActions"] = program_rule_actions_payload
        if program_rule_variables_payload:
            full_payload["programRuleVariables"] = program_rule_variables_payload
        if self.data_elements:
            full_payload["dataElements"] = list(self.data_elements.values())
        if self.options:
            full_payload["options"] = list(self.options.values())
        if self.option_sets:
            full_payload["optionSets"] = list(self.option_sets.values())
        if self.sections:
            # Remove activity_ref from sections before serialization
            sections_payload = []
            for section in self.sections.values():
                section_copy = dict(section)
                if "activity_ref" in section_copy:
                    del section_copy["activity_ref"]
                sections_payload.append(section_copy)
            full_payload["programStageSections"] = sections_payload

        # Export everything to a single file
        metadata_file = os.path.join(base_path, f"{form_id}_metadata.json")
        with open(metadata_file, 'w') as f:
            json.dump(full_payload, f, indent=2)
        logger.info(f"Exported complete DHIS2 metadata to {metadata_file}")

    def get_tricc_operation_operand(self, r):
        if isinstance(r, TriccOperation):
            return self.get_tricc_operation_expression(r)
        elif isinstance(r, TriccReference):
            # Use DHIS2 ID from concept_map instead of name
            node_id = self.concept_map.get(r.value.name, self.get_export_name(r.value))
            return f"#{{{node_id}}}"
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
            return str(r)
        elif isinstance(r, TriccNodeSelectOption):
            option = self.get_option_value(r.name)
            if r.name in ('true', 'false'):
                return option
            return f"'{option}'"
        elif issubclass(r.__class__, TriccNodeDisplayCalculateBase):
            # Use DHIS2 ID from concept_map instead of name
            node_id = self.concept_map.get(r.name, self.get_export_name(r))
            return f"#{node_id}"
        elif issubclass(r.__class__, TriccNodeInputModel):
            # Use DHIS2 ID from concept_map instead of name
            node_id = self.concept_map.get(r.name, self.get_export_name(r))
            return f"#{{{node_id}}}"
        elif issubclass(r.__class__, TriccNodeBaseModel):
            # Use DHIS2 ID from concept_map instead of name
            node_id = self.concept_map.get(r.name, self.get_export_name(r))
            return f"#{{{node_id}}}"
        else:
            raise NotImplementedError(f"This type of node {r.__class__.__name__} is not supported within an operation")

    def convert_expression_to_string(self, expression):
        if isinstance(expression, TriccOperation):
            return self.get_tricc_operation_expression(expression)
        else:
            return self.get_tricc_operation_operand(expression)

    # Operation methods for DHIS2 expressions
    def tricc_operation_equal(self, ref_expressions):
        return f"{ref_expressions[0]} == {ref_expressions[1]}"

    def tricc_operation_not_equal(self, ref_expressions):
        return f"{ref_expressions[0]} != {ref_expressions[1]}"

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
        # For DHIS2, check if value is selected in multi-select
        return f"d2:hasValue({ref_expressions[0]}) && d2:contains({ref_expressions[0]}, {ref_expressions[1]})"

    def tricc_operation_count(self, ref_expressions):
        return f"d2:count({ref_expressions[0]})"

    def tricc_operation_multiplied(self, ref_expressions):
        return "*".join(ref_expressions)

    def tricc_operation_divided(self, ref_expressions):
        return f"{ref_expressions[0]} / {ref_expressions[1]}"

    def tricc_operation_modulo(self, ref_expressions):
        return f"{ref_expressions[0]} % {ref_expressions[1]}"

    def tricc_operation_coalesce(self, ref_expressions):
        return f"d2:coalesce({','.join(ref_expressions)})"

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
        return f"{ref_expressions[0]} >= {ref_expressions[1]} && {ref_expressions[0]} < {ref_expressions[2]}"

    def tricc_operation_isnull(self, ref_expressions):
        return f"!d2:hasValue({ref_expressions[0]})"

    def tricc_operation_isnotnull(self, ref_expressions):
        return f"d2:hasValue({ref_expressions[0]})"

    def tricc_operation_isnottrue(self, ref_expressions):
        return f"{ref_expressions[0]} != true"

    def tricc_operation_isnotfalse(self, ref_expressions):
        return f"{ref_expressions[0]} != false"

    def tricc_operation_notexist(self, ref_expressions):
        return f"!d2:hasValue({ref_expressions[0]})"

    def tricc_operation_case(self, ref_expressions):
        # Simplified case handling
        parts = []
        for i in range(0, len(ref_expressions), 2):
            if i + 1 < len(ref_expressions):
                parts.append(f"if({ref_expressions[i]}, {ref_expressions[i+1]})")
        return " || ".join(parts)

    def tricc_operation_ifs(self, ref_expressions):
        return self.tricc_operation_case(ref_expressions[1:])

    def tricc_operation_if(self, ref_expressions):
        return f"if({ref_expressions[0]}, {ref_expressions[1]}, {ref_expressions[2]})"

    def tricc_operation_contains(self, ref_expressions):
        return f"d2:contains({ref_expressions[0]}, {ref_expressions[1]})"

    def tricc_operation_exists(self, ref_expressions):
        parts = []
        for ref in ref_expressions:
            parts.append(f"d2:hasValue({ref})")
        return " && ".join(parts)

    def tricc_operation_cast_number(self, ref_expressions):
        return f"d2:toNumber({ref_expressions[0]})"

    def tricc_operation_cast_integer(self, ref_expressions):
        return f"d2:toNumber({ref_expressions[0]})"

    def tricc_operation_zscore(self, ref_expressions):
        # Placeholder - would need specific implementation
        return f"zscore({','.join(ref_expressions)})"

    def tricc_operation_datetime_to_decimal(self, ref_expressions):
        return f"d2:daysBetween({ref_expressions[0]}, '1970-01-01')"

    def tricc_operation_round(self, ref_expressions):
        return f"d2:round({ref_expressions[0]})"

    def tricc_operation_izscore(self, ref_expressions):
        return f"izscore({','.join(ref_expressions)})"

    def tricc_operation_concatenate(self, ref_expressions):
        return f"d2:concatenate({','.join(ref_expressions)})"
