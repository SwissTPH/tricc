import datetime
import logging
import os
import shutil
import subprocess
import tempfile
import zipfile
import pandas as pd

from pyxform.xls2xform import convert

from tricc_oo.models.lang import SingletonLangClass
from tricc_oo.models.calculate import TriccNodeEnd
from tricc_oo.models.tricc import TriccNodeDisplayModel
from tricc_oo.serializers.xls_form import (
    SURVEY_MAP,
    get_input_line,
    get_input_calc_line,
)
from tricc_oo.strategies.output.xlsform_cdss import XLSFormCDSSStrategy
from tricc_oo.converters.tricc_to_xls_form import get_export_name
from tricc_oo.converters.utils import clean_name, remove_html
from tricc_oo.visitors.xform_pd import make_breakpoints, get_task_js

langs = SingletonLangClass()
logger = logging.getLogger("default")


class XLSFormCHTStrategy(XLSFormCDSSStrategy):
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
            df_input.loc[len(df_input)] = get_input_calc_line(input)

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
        if not len(df_input[df_input["name"] == "date_of_birth"]):
            df_input.loc[len(df_input)] = [
                "hidden",
                "date_of_birth",
                *list(langs.get_trads("Date of birth", force_dict=True).values()),
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
            "patient_dob",
            *list(langs.get_trads("Date of birth", force_dict=True).values()),
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
            "date(../inputs/contact/date_of_birth)",
            "",
            "",
            "",
            "",
        ]

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
        form_id = None
        if start_pages[self.processes[0]].root.form_id is not None:
            form_id = str(start_pages[self.processes[0]].root.form_id)
        else:
            logger.critical("form id required in the first start node")
            exit(1)
        title = remove_html(start_pages[self.processes[0]].root.label)
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
            "default_language": "English (en)",
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
        # pause
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
                    "default_language": "English (en)",
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

        # create relevance Expression

        # create calculate Expression
        self.process_calculate(self.project.start_pages, pages=self.project.pages)
        logger.info("generate the export format")
        # create calculate Expression
        self.process_export(self.project.start_pages, pages=self.project.pages)

        logger.info("print the export")

        # Export returns list of generated files for CHT strategy
        generated_files = self.export(self.project.start_pages, version=version)

        logger.info("validate the output")
        if not self.validate(generated_files):
            logger.error("CHT validation failed - aborting build")
            exit(1)

    def validate(self, generated_files=None):
        """Validate the generated XLS form(s) using pyxform conversion and ODK Validate JAR."""
        if generated_files is None:
            # Fallback for single file validation
            if self.project.start_pages["main"].root.form_id is not None:
                form_id = str(self.project.start_pages["main"].root.form_id)
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
                with tempfile.NamedTemporaryFile(mode='w', suffix='.xml', delete=False) as temp_file:
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

                jar_in_zip = "site-packages/pyxform/validators/odk_validate/bin/ODK_Validate.jar"
                zip_ref.extract(jar_in_zip, os.path.dirname(__file__))

                # Move to final location
                extracted_jar = os.path.join(os.path.dirname(__file__), jar_in_zip)
                shutil.move(extracted_jar, jar_path)

            logger.info(f"Extracted ODK Validate JAR to {jar_path}")
            return jar_path

    def _ensure_odk_validate_jar(self):
        """Ensure ODK Validate JAR is available by downloading from GitHub releases."""
        jar_path = os.path.join(os.path.dirname(__file__), "ODK_Validate.jar")

        # Check if JAR already exists
        if os.path.exists(jar_path):
            return jar_path

        # Download JAR from GitHub releases
        jar_url = "https://github.com/getodk/validate/releases/download/v1.19.2/validate.jar"
        try:
            import urllib.request
            urllib.request.urlretrieve(jar_url, jar_path)
            logger.info(f"Downloaded ODK Validate JAR to {jar_path}")
            return jar_path
        except Exception as e:
            logger.error(f"Failed to download ODK Validate JAR: {str(e)}")
            return None

    def tricc_operation_zscore(self, ref_expressions):
        y, ll, m, s = self.get_zscore_params(ref_expressions)
        #  return ((Math.pow((y / m), l) - 1) / (s * l));
        return f"""cht:extension-lib('{
            ref_expressions[0][1:-1]
            }.js',{
            self.clean_coalesce(ref_expressions[1])
            } ,{
            self.clean_coalesce(ref_expressions[2])
            } ,{
            self.clean_coalesce(ref_expressions[3])
            })"""

    def tricc_operation_izscore(self, ref_expressions):
        z, ll, m, s = self.get_zscore_params(ref_expressions)
        #  return  (m * (z*s*l-1)^(1/l));
        return f"""cht:extension-lib('{
            ref_expressions[0][1:-1]
            }.js',{
            self.clean_coalesce(ref_expressions[1])
            } ,{
            self.clean_coalesce(ref_expressions[2])
            } ,{
            self.clean_coalesce(ref_expressions[3])
            }, true"""

    def tricc_operation_drug_dosage(self, ref_expressions):
        # drug name
        # age
        # weight
        return f"cht:extension-lib('drugs.js',{','.join(map(self.clean_coalesce, ref_expressions))})"
