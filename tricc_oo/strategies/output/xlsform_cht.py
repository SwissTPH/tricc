import datetime
import json
import logging
import os
import shutil
import subprocess
import tempfile
import zipfile
from typing import Optional
import pandas as pd

from pyxform.xls2xform import convert

from tricc_oo.models.lang import SingletonLangClass
from tricc_oo.converters.fhir.populate_helper import populate_uses_inputs_group
from tricc_oo.models.calculate import TriccNodeEnd, TriccNodePopulate
from tricc_oo.models.base import TriccOperation, TriccReference
from tricc_oo.models.tricc import TriccNodeDisplayModel
from tricc_oo.serializers.xls_form import (
    SURVEY_MAP,
    get_input_line,
    get_input_calc_line,
    get_populate_calc_line,
)
from tricc_oo.strategies.output.xlsform_cdss import XLSFormCDSSStrategy
from tricc_oo.strategies.registry import register_output_strategy
from tricc_oo.strategies.output.xls_form import XLSFormStrategy
from tricc_oo.converters.cql_to_operation import transform_cql_to_operation
from tricc_oo.converters.duration import to_days
from tricc_oo.converters.tricc_to_xls_form import get_export_name
from tricc_oo.converters.utils import clean_name, remove_html
from tricc_oo.serializers.js_expression import render_cht_js_expression
from tricc_oo.visitors.text_injection import serialize_injection_for_js_text
from tricc_oo.visitors.xform_pd import make_breakpoints, get_task_js

langs = SingletonLangClass()
logger = logging.getLogger("default")


def _cht_condition_reference_names(node):
    names = []
    if isinstance(node, TriccReference):
        names.append(str(node.value))
    elif isinstance(node, TriccOperation):
        for item in node.reference or []:
            names.extend(_cht_condition_reference_names(item))
    elif isinstance(node, list):
        for item in node:
            names.extend(_cht_condition_reference_names(item))
    return names


@register_output_strategy("XLSFormCHTStrategy")
class XLSFormCHTStrategy(XLSFormCDSSStrategy):
    # decision table calls stay calls: cht:extension-lib('dmn-<project>.js', …), the library
    # written next to the forms (feature/20261123-decision-tables.md)
    decision_table_calls = True
    def generate_export(self, node, **kwargs):
        # CDSS-only coalesce/$this handling must not run for CHT exports.
        return XLSFormStrategy.generate_export(self, node, **kwargs)

    def process_export(self, start_pages, **kwargs):
        self.activity_export(start_pages[self.processes[0]], **kwargs)
        # self.add_tab_breaks_choice()
        cht_input_df = self.get_cht_input(start_pages, **kwargs)
        self.df_survey = self.df_survey[~self.df_survey["name"].isin(cht_input_df["name"])]
        self.df_survey.reset_index(drop=True, inplace=True)

        self.df_survey = pd.concat([cht_input_df, self.df_survey, self.get_cht_summary()], ignore_index=True)

        self.inject_version()

    def get_empty_label(self):
        return "NO_LABEL"

    def retrieval_expression(self, retrieval) -> str:
        """CHT calculation of a project retrieval.

        Every catalogue function reads the contact summary, like populate nodes:
        ``instance('contact-summary')/context/<name>`` (the deployment's contact-summary
        script provides ``<name>``). ``custom`` uses its ``text/x-xlsform`` expression.
        """
        if retrieval.effective_function is None:
            return super().retrieval_expression(retrieval)
        if retrieval.effective_function == "LatestDate":
            warned = self.__dict__.setdefault("_retrieval_date_warned", set())
            if retrieval.code not in warned:
                warned.add(retrieval.code)
                logger.warning(
                    f"retrieval {retrieval.code}: the CHT contact summary must expose the date of the latest "
                    f"'{retrieval.reads_code}' record as '{retrieval.name}' (feature/20261125-populate-read-date.md)"
                )
        return f"coalesce(instance('contact-summary')/context/{retrieval.name},'')"

    def get_cht_input(self, start_pages, **kwargs):
        empty = langs.get_trads("", force_dict=True)
        df_input = pd.DataFrame(columns=SURVEY_MAP.keys())
        # [ #type, '',#name ''#label, '',#hint '',#help '',#default '',#'appearance',
        # '',#'constraint',  '',#'constraint_message' '',#'relevance' '',#'disabled'
        # '',#'required' '',#'required message' '',#'read only' '',#'expression' '',#
        # 'repeat_count' ''#'image' ],
        df_input.loc[len(df_input)] = [
            "begin_group",
            "inputs",
            *list(langs.get_trads("NO_LABEL", force_dict=True).values()),
            *list(empty.values()),
            *list(empty.values()),
            "",
            "field-list",
            "",
            *list(empty.values()),
            './source = "user"',
            "",
            "",
            *list(empty.values()),
            "",
            "",
            "",
            "",
            "",
            "",
        ]
        df_input.loc[len(df_input)] = [
            "hidden",
            "source",
            *list(langs.get_trads("Source", force_dict=True).values()),
            *list(empty.values()),
            *list(empty.values()),
            "user",
            "hidden",
            "",
            *list(empty.values()),
            "",
            "",
            "",
            *list(empty.values()),
            "",
            "",
            "",
            "",
            "",
            "",
        ]
        df_input.loc[len(df_input)] = [
            "hidden",
            "source_id",
            *list(langs.get_trads("Source ID", force_dict=True).values()),
            *list(empty.values()),
            *list(empty.values()),
            "",
            "hidden",
            "",
            *list(empty.values()),
            "",
            "",
            "",
            *list(empty.values()),
            "",
            "",
            "",
            "",
            "",
            "",
        ]

        df_input.loc[len(df_input)] = [
            "begin_group",
            "user",
            *list(langs.get_trads("NO_LABEL", force_dict=True).values()),
            *list(empty.values()),
            *list(empty.values()),
            "",
            "field-list",
            "",
            *list(empty.values()),
            "",
            "",
            "",
            *list(empty.values()),
            "",
            "",
            "",
            "",
            "",
            "",
        ]
        df_input.loc[len(df_input)] = [
            "string",
            "contact_id",
            *list(langs.get_trads("NO_LABEL", force_dict=True).values()),
            *list(empty.values()),
            *list(empty.values()),
            "",
            "hidden",
            "",
            *list(empty.values()),
            "",
            "",
            "",
            *list(empty.values()),
            "",
            "",
            "",
            "",
            "",
            "",
        ]
        df_input.loc[len(df_input)] = [
            "string",
            "facility_id",
            *list(langs.get_trads("NO_LABEL", force_dict=True).values()),
            *list(empty.values()),
            *list(empty.values()),
            "",
            "hidden",
            "",
            *list(empty.values()),
            "",
            "",
            "",
            *list(empty.values()),
            "",
            "",
            "",
            "",
            "",
            "",
        ]
        df_input.loc[len(df_input)] = [
            "string",
            "name",
            *list(langs.get_trads("NO_LABEL", force_dict=True).values()),
            *list(empty.values()),
            *list(empty.values()),
            "",
            "hidden",
            "",
            *list(empty.values()),
            "",
            "",
            "",
            *list(empty.values()),
            "",
            "",
            "",
            "",
            "",
            "",
        ]
        df_input.loc[len(df_input)] = [
            "end_group",
            "user end",
            *list(empty.values()),
            *list(empty.values()),
            *list(empty.values()),
            "",
            "",
            "",
            *list(empty.values()),
            "",
            "",
            "",
            *list(empty.values()),
            "",
            "",
            "",
            "",
            "",
            "",
        ]
        df_input.loc[len(df_input)] = [
            "begin_group",
            "contact",
            *list(langs.get_trads("NO_LABEL", force_dict=True).values()),
            *list(empty.values()),
            *list(empty.values()),
            "",
            "field-list",
            "",
            *list(empty.values()),
            "",
            "",
            "",
            *list(empty.values()),
            "",
            "",
            "",
            "",
            "",
            "",
        ]
        inputs = self.export_inputs(start_pages[self.processes[0]], **kwargs)
        for input in inputs:
            # Only values CHT injects through the `inputs` group get a hidden field
            # here, named after the source document field. Contact-summary backed
            # values never pass through `inputs` — they only need their calculate row
            # (fix/20260821-merge-input-into-populate.md).
            if populate_uses_inputs_group(input):
                df_input.loc[len(df_input)] = get_input_line(input)
        self.get_contact_inputs(df_input)
        df_input.loc[len(df_input)] = [
            "hidden",
            "external_id",
            *list(langs.get_trads("NO_LABEL", force_dict=True).values()),
            *list(empty.values()),
            *list(empty.values()),
            "",
            "hidden",
            "",
            *list(empty.values()),
            "",
            "",
            "",
            *list(empty.values()),
            "",
            "",
            "",
            "",
            "",
            "",
        ]

        df_input.loc[len(df_input)] = [
            "string",
            "_id",
            *list(langs.get_trads("NO_LABEL", force_dict=True).values()),
            *list(empty.values()),
            *list(empty.values()),
            "",
            "hidden",
            "",
            *list(empty.values()),
            "",
            "",
            "",
            *list(empty.values()),
            "",
            "",
            "",
            "",
            "",
            "",
        ]

        df_input.loc[len(df_input)] = [
            "end_group",
            "contact end",
            *list(empty.values()),
            *list(empty.values()),
            *list(empty.values()),
            "",
            "",
            "",
            *list(empty.values()),
            "",
            "",
            "",
            *list(empty.values()),
            "",
            "",
            "",
            "",
            "",
            "",
        ]

        df_input.loc[len(df_input)] = [
            "end_group",
            "input end",
            *list(empty.values()),
            *list(empty.values()),
            *list(empty.values()),
            "",
            "",
            "",
            *list(empty.values()),
            "",
            "",
            "",
            *list(empty.values()),
            "",
            "",
            "",
            "",
            "",
            "",
        ]

        df_input.loc[len(df_input)] = [
            "hidden",
            "data_load",
            *list(langs.get_trads("NO_LABEL", force_dict=True).values()),
            *list(empty.values()),
            *list(empty.values()),
            "",
            "hidden",
            "",
            *list(empty.values()),
            "",
            "",
            "",
            *list(empty.values()),
            "",
            "",
            "",
            "",
            "",
            "",
        ]
        self.get_contact_inputs_calculate(df_input)
        df_input.loc[len(df_input)] = [
            "calculate",
            "created_by_person_uuid",
            *list(empty.values()),
            *list(empty.values()),  # hint
            *list(empty.values()),  # help
            "",  # default
            "",  # 'appearance', clean_name
            "",  # 'constraint',
            *list(empty.values()),  # 'constraint_message'
            "",  # 'relevance'
            "",  # 'disabled'
            "",  # 'required'
            *list(empty.values()),  # 'required message'
            "",  # 'read only'
            "../inputs/user/contact_id",  # 'expression'
            "",
            "",  # 'repeat_count'
            "",  # 'image'
            "",  # choice filter
        ]
        df_input.loc[len(df_input)] = [
            "calculate",
            "created_by_place_uuid_user",
            *list(empty.values()),
            *list(empty.values()),  # hint
            *list(empty.values()),  # help
            "",  # default
            "",  # 'appearance', clean_name
            "",  # 'constraint',
            *list(empty.values()),  # 'constraint_message'
            "",  # 'relevance'
            "",  # 'disabled'
            "",  # 'required'
            *list(empty.values()),  # 'required message'
            "",  # 'read only'
            "../inputs/user/facility_id",  # 'expression'
            "",
            "",  # 'repeat_count'
            "",  # 'image'
            "",  # choice filter
        ]
        df_input.loc[len(df_input)] = [
            "calculate",
            "created_by",
            *list(empty.values()),
            *list(empty.values()),  # hint
            *list(empty.values()),  # help
            "",  # default
            "",  # 'appearance', clean_name
            "",  # 'constraint',
            *list(empty.values()),  # 'constraint_message'
            "",  # 'relevance'
            "",  # 'disabled'
            "",  # 'required'
            *list(empty.values()),  # 'required message'
            "",  # 'read only'
            "../inputs/user/name",  # 'expression'
            "",
            "",  # 'repeat_count'
            "",  # 'image'
            "",  # choice filter
        ]
        df_input.loc[len(df_input)] = [
            "calculate",
            "created_by_place_uuid",
            *list(empty.values()),
            *list(empty.values()),  # hint
            *list(empty.values()),  # help
            "",  # default
            "",  # 'appearance', clean_name
            "",  # 'constraint',
            *list(empty.values()),  # 'constraint_message'
            "",  # 'relevance'
            "",  # 'disabled'
            "",  # 'required'
            *list(empty.values()),  # 'required message'
            "",  # 'read only'
            "../inputs/contact/_id",  # 'expression'
            "",
            "",  # 'repeat_count'
            "",  # 'image'
            "",  # choice filter
        ]

        df_input.loc[len(df_input)] = [
            "calculate",
            "source_id",
            *list(empty.values()),
            *list(empty.values()),  # hint
            *list(empty.values()),  # help
            "",  # default
            "",  # 'appearance', clean_name
            "",  # 'constraint',
            *list(empty.values()),  # 'constraint_message'
            "",  # 'relevance'
            "",  # 'disabled'
            "",  # 'required'
            *list(empty.values()),  # 'required message'
            "",  # 'read only'
            "../inputs/source_id",  # 'expression'
            "",
            "",  # 'repeat_count'
            "",  # 'image'
            "",  # choice filter
        ]
        df_input.loc[len(df_input)] = [
            "calculate",
            "patient_uuid",
            *list(empty.values()),
            *list(empty.values()),  # hint
            *list(empty.values()),  # help
            "",  # default
            "",  # 'appearance', clean_name
            "",  # 'constraint',
            *list(empty.values()),  # 'constraint_message'
            "",  # 'relevance'
            "",  # 'disabled'
            "",  # 'required'
            *list(empty.values()),  # 'required message'
            "",  # 'read only'
            "../inputs/user/facility_id",  # 'expression'
            "",
            "",  # 'repeat_count'
            "",  # 'image'
            "",  # choice filter
        ]

        for input in inputs:
            if populate_uses_inputs_group(input):
                # reads ../inputs/contact/<source field>
                df_input.loc[len(df_input)] = get_input_calc_line(input)
            else:
                # reads instance('contact-summary')/context/<key>
                df_input.loc[len(df_input)] = get_populate_calc_line(input)
        # project retrievals, next to the populate values (feature/20261109-project-retrievals.md)
        for row in self.get_retrieval_lines():
            df_input.loc[len(df_input)] = row
        self._retrievals_injected = True

        return df_input

    def get_contact_inputs(self, df_input):
        empty = langs.get_trads("", force_dict=True)
        if not len(df_input[df_input["name"] == "sex"]):
            df_input.loc[len(df_input)] = [
                "hidden",
                "sex",
                *list(langs.get_trads("Sex", force_dict=True).values()),
                *list(empty.values()),
                *list(empty.values()),
                "",
                "hidden",
                "",
                *list(empty.values()),
                "",
                "",
                "",
                *list(empty.values()),
                "",
                "",
                "",
                "",
                "",
                "",
            ]
        if not len(df_input[df_input["name"] == "name"]):
            df_input.loc[len(df_input)] = [
                "hidden",
                "name",
                *list(langs.get_trads("Name", force_dict=True).values()),
                *list(empty.values()),
                *list(empty.values()),
                "",
                "hidden",
                "",
                *list(empty.values()),
                "",
                "",
                "",
                *list(empty.values()),
                "",
                "",
                "",
                "",
                "",
                "",
            ]
        ## TODO We removed date_of_birth from header to not overwrite from drawing @pdx let us know if this is required
        #f not len(df_input[df_input["name"] == "date_of_birth"]):
        #   df_input.loc[len(df_input)] = [
        #       "hidden",
        #       "date_of_birth",
        #       *list(langs.get_trads("Date of birth", force_dict=True).values()),
        #       *list(empty.values()),
        #       *list(empty.values()),
        #       "",
        #       "hidden",
        #       "",
        #       *list(empty.values()),
        #       "",
        #       "",
        #       "",
        #       *list(empty.values()),
        #       "",
        #       "",
        #       "",
        #       "",
        #       "",
        #       "",
        #   ]

        return df_input

    def get_contact_inputs_calculate(self, df_input):
        empty = langs.get_trads("", force_dict=True)
        df_input.loc[len(df_input)] = [
            "calculate",
            "patient_sex",
            *list(langs.get_trads("Sex", force_dict=True).values()),
            *list(empty.values()),
            *list(empty.values()),
            "",
            "hidden",
            "",
            *list(empty.values()),
            "",
            "",
            "",
            *list(empty.values()),
            "",
            "../inputs/contact/sex",
            "",
            "",
            "",
            "",
        ]
        df_input.loc[len(df_input)] = [
            "calculate",
            "patient_name",
            *list(langs.get_trads("Name", force_dict=True).values()),
            *list(empty.values()),
            *list(empty.values()),
            "",
            "hidden",
            "",
            *list(empty.values()),
            "",
            "",
            "",
            *list(empty.values()),
            "",
            "../inputs/contact/patient_name",
            "",
            "",
            "",
            "",
        ]
        
                ## TODO We removed patient_dob from header because it refers to the removed dob @pdx let us know if this is required

        #df_input.loc[len(df_input)] = [
        #    "calculate",
        #    "patient_dob",
        #    *list(langs.get_trads("Date of birth", force_dict=True).values()),
        #    *list(empty.values()),
        #    *list(empty.values()),
        #    "",
        #    "hidden",
        #    "",
        #    *list(empty.values()),
        #    "",
        #    "",
        #    "",
        #    *list(empty.values()),
        #    "",
        #    "coalesce(date(../inputs/contact/date_of_birth),today())",
        #    "",
        #    "",
        #    "",
        #    "",
        #]

        return df_input

    def get_cht_summary(self):
        df_summary = pd.DataFrame(columns=SURVEY_MAP.keys())
        return df_summary

    def get_last_prev_index(self, df, e, depth=0):
        latest = None
        for p in e.prev_nodes:
            if issubclass(p.__class__, (TriccNodeDisplayModel)):
                if hasattr(p, "select"):
                    p = latest.select
                index = df.index[df["name"] == get_export_name(p)].tolist()

                if not latest or (index and index[-1] > latest):
                    latest = index[-1]
        if latest is None and depth > 5:
            for p in e.prev_nodes:
                index = self.get_last_prev_index(df, e, depth + 1)
                if not latest and index and index > latest:
                    latest = index
        return latest

    def export(self, start_pages, version, **kwargs):
        self.apply_translations()
        form_id = self.project.intervention_name()
        if not form_id:
            logger.critical("form id required: set interventions[].name (or a project title)")
            exit(1)
        root_label = start_pages[self.processes[0]].root.label
        if isinstance(root_label, str):
            title = remove_html(root_label)
        else:
            title = serialize_injection_for_js_text(root_label)
        if self.project is not None:
            title = self.project.export_form_title(title)
        self._form_id = form_id
        self._cht_title = title
        file_name = form_id + ".xlsx"
        # make a 'settings' tab
        now = datetime.datetime.now()
        version = now.strftime("%Y%m%d%H%M")
        indx = [[1]]
        # CHT FORCE file name to be equal to id

        newfilename = form_id + ".xlsx"
        newpath = os.path.join(self.output_path, newfilename)
        media_path = os.path.join(self.output_path, form_id + "-media")

        # Track all generated XLS files for validation
        generated_files = [newpath]

        settings = {
            "form_title": title,
            "form_id": form_id,
            "version": version,
            "default_language": self.default_language_setting(),
            "style": "pages",
        }
        df_settings = pd.DataFrame(settings, index=indx)
        df_settings.head()
        # create a Pandas Excel writer using XlsxWriter as the engine
        writer = pd.ExcelWriter(newpath, engine="xlsxwriter")
        self.df_survey.to_excel(writer, sheet_name="survey", index=False)
        self.df_choice.to_excel(writer, sheet_name="choices", index=False)
        df_settings.to_excel(writer, sheet_name="settings", index=False)
        writer.close()
        self._write_demand_properties(form_id, title)
        # pause
        logger.info("generating the task and after pause questionnaires")
        ends = []
        for p in self.project.pages.values():
            p_ends = list(
                filter(
                    lambda x: issubclass(x.__class__, TriccNodeEnd) and getattr(x, "process", "") == "pause",
                    p.nodes.values(),
                )
            )
            if p_ends:
                ends += p_ends
        if ends:
            ends_prev = []
            for e in ends:
                latest = self.get_last_prev_index(self.df_survey, e)
                if latest:
                    ends_prev.append(
                        (
                            int(latest),
                            e,
                        )
                    )
                else:
                    logger.critical(f"impossible to get last index before pause: {e.get_name()}")
            forms = [form_id]
            for i, e in ends_prev:
                new_form_id = f"{form_id}_{clean_name(e.name)}"
                newfilename = f"{new_form_id}.xlsx"
                newpath = os.path.join(self.output_path, newfilename)
                generated_files.append(newpath)  # Track additional XLS files
                settings = {
                    "form_title": title,
                    "form_id": f"{new_form_id}",
                    "version": version,
                    "default_language": self.default_language_setting(),
                    "style": "pages",
                }
                df_settings = pd.DataFrame(settings, index=indx)
                df_settings.head()
                task_df, hidden_names = make_breakpoints(self.df_survey, i, e.name, replace_dots=True)
                # deactivate the end node
                task_df.loc[task_df["name"] == get_export_name(e), "calculation"] = 0
                # print fileds
                writer = pd.ExcelWriter(newpath, engine="xlsxwriter")
                task_df.to_excel(writer, sheet_name="survey", index=False)
                self.df_choice.to_excel(writer, sheet_name="choices", index=False)
                df_settings.to_excel(writer, sheet_name="settings", index=False)
                writer.close()
                newfilename = f"{new_form_id}.js"
                newpath = os.path.join(self.output_path, newfilename)
                with open(newpath, "w") as f:
                    f.write(
                        get_task_js(
                            new_form_id,
                            e.name,
                            f"continue {title}",
                            forms,
                            hidden_names,
                            self.df_survey,
                            repalce_dots=False,
                            task_title=e.hint,
                        )
                    )
                    f.close()
                forms.append(new_form_id)

        media_path_tmp = os.path.join(self.output_path, "media-tmp")
        if os.path.isdir(media_path_tmp):
            if os.path.isdir(media_path):  # check if it exists, because if it does, error will be raised
                shutil.rmtree(media_path)
                # (later change to make folder complaint to CHT)
            os.mkdir(media_path)

            file_names = os.listdir(media_path_tmp)
            for file_name in file_names:
                shutil.move(os.path.join(media_path_tmp, file_name), media_path)
            shutil.rmtree(media_path_tmp)

        return generated_files

    def execute(self):
        """Override execute to handle multiple output files from CHT strategy."""
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
        # create calculate Expression
        self.process_export(self.project.start_pages, pages=self.project.pages)

        logger.info("print the export")

        # Export returns list of generated files for CHT strategy
        generated_files = self.export(self.project.start_pages, version=version)
        self.write_decision_table_library()
        self.write_contact_summary_keys()

        logger.info("validate the output")
        if not self.validate(generated_files):
            logger.error("CHT validation failed - aborting build")
            exit(1)

    def decision_table_library(self) -> str:
        """The project's decision table library: ``dmn-<project>.js``."""
        from tricc_oo.serializers.dmn_js import library_name

        return library_name(getattr(self.project, "title", None))

    def table_call_expression(self, operation):
        """``cht:extension-lib('dmn-<project>.js', 'table', 'policy', 'output', input1, …)``.

        Each input is read once; the library evaluates the table (tricc_oo.serializers.dmn_js).
        """
        table_id, policy, output = (r.value for r in operation.reference[1:4])
        self.check_list_values((getattr(self.project, "decision_tables", None) or {}).get(table_id), policy, output)
        args = [self.table_call_operand(arg) for arg in operation.reference[4:]]
        self._decision_table_calls = True
        head = ", ".join(f"'{v}'" for v in (table_id, policy, output))
        return f"cht:extension-lib('{self.decision_table_library()}', {head}, {', '.join(args)})"

    def write_decision_table_library(self) -> Optional[str]:
        """Write ``extension-libs/dmn-<project>.js`` when a form calls a table; returns its path.

        Every table of the project goes in, so the file is the same for each intervention.
        """
        if not getattr(self, "_decision_table_calls", False):
            return None
        from tricc_oo.serializers.dmn_js import build_dmn_js

        folder = os.path.join(self.output_path, "extension-libs")
        os.makedirs(folder, exist_ok=True)
        path = os.path.join(folder, self.decision_table_library())
        with open(path, "w", encoding="utf-8") as handle:
            handle.write(build_dmn_js(self.project.decision_tables, getattr(self.project, "title", None)))
        logger.info(f"decision tables written to {path}: upload with cht-conf upload-extension-libs")
        return path

    def write_contact_summary_keys(self) -> Optional[str]:
        """Write ``<form>.contact-summary.json``: the contact-summary keys the form reads, grouped
        by concept, scope and window, so the deployment's contact-summary script reads each
        concept once (feature/20261125-requires-and-implied-retrievals.md §4).

        Returns:
            The path written, or None when the form reads no contact-summary key.
        """
        from tricc_oo.converters.fhir.populate_helper import populate_source_concept
        from tricc_oo.converters.retrieval import contact_summary_keys, is_retrieval_node, iter_retrievals
        from tricc_oo.converters.tricc_to_xls_form import _concept_export_base_name

        populates = []
        for page in (getattr(self.project, "pages", None) or {}).values():
            for node in (getattr(page, "nodes", None) or {}).values():
                if (
                    isinstance(node, TriccNodePopulate)
                    and not is_retrieval_node(node)
                    and node.context in ("history",)
                    and not populate_uses_inputs_group(node)
                ):
                    key = _concept_export_base_name(node)
                    populates.append((key, populate_source_concept(node), node.context, node.period))
        keys = contact_summary_keys(iter_retrievals(self.project), sorted(set(populates)))
        if not keys["concepts"] and not keys["other"]:
            return None
        form_id = getattr(self, "_form_id", None) or self.project.intervention_name()
        path = os.path.join(self.output_path, f"{form_id}.contact-summary.json")
        with open(path, "w", encoding="utf-8") as handle:
            json.dump({"form": form_id, **keys}, handle, indent=2, ensure_ascii=False)
            handle.write("\n")
        logger.info("Wrote CHT contact-summary keys: %s", path)
        return path

    def _write_demand_properties(self, form_id, title):
        intervention = getattr(self.project, "config", None)
        condition = intervention.demand_condition() if intervention is not None else None
        if not condition:
            return
        parsed = transform_cql_to_operation(condition, context=f"start.condition for {form_id}")
        if parsed is None:
            raise ValueError(f"start.condition is not valid CQL: {condition}")
        expression = render_cht_js_expression(parsed)
        payload = {
            "title": title,
            "context": {
                "person": True,
                "place": False,
                "expression": expression,
            },
        }
        path = os.path.join(self.output_path, f"{form_id}.properties.json")
        with open(path, "w", encoding="utf-8") as handle:
            json.dump(payload, handle, indent=2, ensure_ascii=False)
            handle.write("\n")
        logger.info("Wrote CHT properties.json: %s", path)

    def _rewrite_xlsx(self, form_id, title):
        path = os.path.join(self.output_path, f"{form_id}.xlsx")
        version = datetime.datetime.now().strftime("%Y%m%d%H%M")
        settings = {
            "form_title": title,
            "form_id": form_id,
            "version": version,
            "default_language": self.default_language_setting(),
            "style": "pages",
        }
        df_settings = pd.DataFrame(settings, index=[[1]])
        writer = pd.ExcelWriter(path, engine="xlsxwriter")
        self.df_survey.to_excel(writer, sheet_name="survey", index=False)
        self.df_choice.to_excel(writer, sheet_name="choices", index=False)
        df_settings.to_excel(writer, sheet_name="settings", index=False)
        writer.close()

    def _append_start_calculate(self, child_id, xpath):
        name = f"start_{child_id}"
        row = {column: "" for column in self.df_survey.columns}
        row["type"] = "calculate"
        row["name"] = name
        if "calculation" in row:
            row["calculation"] = xpath
        self.df_survey = pd.concat([self.df_survey, pd.DataFrame([row])], ignore_index=True)
        return name

    def _follow_up_hidden_names(self, child_strategy):
        parent_names = {
            str(name)
            for name in self.df_survey.get("name", pd.Series(dtype=str)).dropna().astype(str)
        }
        hidden = []
        child_df = getattr(child_strategy, "df_survey", None)
        if child_df is None or child_df.empty:
            return hidden
        skip_types = {"begin group", "end group", "note", "calculate"}
        for _, row in child_df.iterrows():
            name = str(row.get("name") or "")
            row_type = str(row.get("type") or "")
            if not name or row_type in skip_types:
                continue
            if name in parent_names:
                hidden.append(name)
        return hidden

    def link_follow_up(self, child_strategy, start) -> None:
        child_intervention = getattr(getattr(child_strategy, "project", None), "config", None)
        child_id = getattr(child_intervention, "id", None)
        if not child_id:
            raise ValueError("follow-up intervention is missing an id")
        parent_form_id = getattr(self, "_form_id", None)
        child_form_id = getattr(child_strategy, "_form_id", None)
        if not parent_form_id or not child_form_id:
            raise ValueError("CHT follow-up requires an intervention name on parent and child")
        applies_field = None
        if start.condition:
            parsed = transform_cql_to_operation(
                start.condition, context=f"start.condition for {child_id}"
            )
            if parsed is None:
                raise ValueError(f"start.condition is not valid CQL: {start.condition}")
            xpath = self.get_tricc_operation_expression(parsed)
            parent_names = set(self.df_survey["name"].dropna().astype(str))
            missing = [
                name
                for name in _cht_condition_reference_names(parsed)
                if name not in parent_names
            ]
            if missing:
                raise ValueError(
                    f"follow-up condition references {missing} which are not in parent form {parent_form_id}"
                )
            applies_field = self._append_start_calculate(child_id, xpath)
            self._rewrite_xlsx(parent_form_id, getattr(self, "_cht_title", parent_form_id))
        hidden_names = self._follow_up_hidden_names(child_strategy)
        window = start.window_or_default()
        days = to_days(start.due or 0)
        start_days = to_days(window.before)
        end_days = to_days(window.after)
        js_path = os.path.join(child_strategy.output_path, f"{child_form_id}.js")
        with open(js_path, "w", encoding="utf-8") as handle:
            handle.write(
                get_task_js(
                    child_form_id,
                    applies_field or "",
                    getattr(child_intervention, "title", child_id),
                    [parent_form_id],
                    hidden_names,
                    self.df_survey,
                    repalce_dots=False,
                    task_title=getattr(child_intervention, "title", child_id),
                    applies_field=applies_field,
                    always_applies=not applies_field,
                    days=days,
                    start=start_days,
                    end=end_days,
                )
            )
        logger.info("Wrote CHT follow-up task module: %s", js_path)

    def validate(self, generated_files=None):
        """Validate the generated XLS form(s) using pyxform conversion and ODK Validate JAR."""
        if generated_files is None:
            # Fallback for single file validation
            form_id = self.project.intervention_name()
            if form_id:
                generated_files = [os.path.join(self.output_path, form_id + ".xlsx")]
            else:
                logger.error("Form ID not found for validation")
                return False

        # Ensure ODK Validate JAR is available
        jar_path = self._ensure_odk_validate_jar()
        if not jar_path:
            logger.error("ODK Validate JAR not available, skipping CHT validation")
            return False

        all_valid = True
        for xls_file in generated_files:
            if not os.path.exists(xls_file):
                logger.error(f"XLS file not found: {xls_file}")
                all_valid = False
                continue

            try:
                # Convert XLS to XForm using pyxform (without validation)
                xform_path = xls_file.replace('.xlsx', '.xml')
                convert_result = convert(
                    xlsform=xls_file,
                    validate=False,  # Don't validate during conversion
                    pretty_print=True
                )
                xform_content = convert_result.xform

                # Write XForm to temporary file for validation
                with tempfile.NamedTemporaryFile(
                    mode='w',
                    encoding='utf-8',
                    suffix='.xml',
                    delete=False
                ) as temp_file:
                    temp_file.write(xform_content)
                    temp_xform_path = temp_file.name

                try:
                    # Run ODK Validate JAR on the XForm
                    result = subprocess.run(
                        ["java", "-Djava.awt.headless=true", "-jar", jar_path, temp_xform_path],
                        capture_output=True,
                        text=True,
                        cwd=self.output_path
                    )

                    if result.returncode == 0 or "Cycle detected" in result.stderr:
                        logger.info(f"CHT XLSForm validation successful: {os.path.basename(xls_file)}")
                    else:
                        logger.error(f"CHT XLSForm validation failed for {os.path.basename(xls_file)}: {result.stderr}")
                        all_valid = False

                finally:
                    # Clean up temporary XForm file
                    os.unlink(temp_xform_path)

            except Exception as e:
                logger.error(f"CHT XLSForm validation error for {os.path.basename(xls_file)}: {str(e)}")
                all_valid = False

            logger.info(f"Extracted ODK Validate JAR to {jar_path}")
            return jar_path

    def _ensure_odk_validate_jar(self):
        """Ensure ODK Validate JAR is available by downloading from GitHub releases."""
        jar_path = os.path.join(os.path.dirname(__file__), "ODK_Validate.jar")

        # Check if JAR already exists
        if os.path.exists(jar_path):
            return jar_path

        # Download JAR from GitHub releases
        jar_url = "https://github.com/getodk/validate/releases/download/v1.20.0/ODK-Validate-v1.20.0.jar"
        try:
            import urllib.request
            urllib.request.urlretrieve(jar_url, jar_path)
            logger.info(f"Downloaded ODK Validate JAR to {jar_path}")
            return jar_path
        except Exception as e:
            logger.error(f"Failed to download ODK Validate JAR: {str(e)}")
            return None

    def tricc_operation_get_inherited_value(self, ref_expressions, original_references=None):  
        """CHT supports coalesce(., …) for the current question value."""
        return self.tricc_operation_coalesce([".", *ref_expressions])
