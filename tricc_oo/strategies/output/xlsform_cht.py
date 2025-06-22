import datetime
import logging
import os
import shutil
import re
import pandas as pd

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
        diags = []
        self.activity_export(start_pages[self.processes[0]], **kwargs)
        # self.add_tab_breaks_choice()
        cht_header = pd.DataFrame(columns=SURVEY_MAP.keys())
        cht_input_df = self.get_cht_input(start_pages, **kwargs)
        self.df_survey = self.df_survey[
            ~self.df_survey["name"].isin(cht_input_df["name"])
        ]
        self.df_survey.reset_index(drop=True, inplace=True)

        self.df_survey = pd.concat(
            [cht_input_df, self.df_survey, self.get_cht_summary()], ignore_index=True
        )

    def get_cht_input(self, start_pages, **kwargs):
        empty = langs.get_trads("", force_dict=True)
        df_input = pd.DataFrame(columns=SURVEY_MAP.keys())
        # [ #type, '',#name ''#label, '',#hint '',#help '',#default '',#'appearance',  '',#'constraint',  '',#'constraint_message' '',#'relevance' '',#'disabled' '',#'required' '',#'required message' '',#'read only' '',#'expression' '',#'repeat_count' ''#'image' ],
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
        ]
        self.get_contact_inputs_calculate(df_input)
        df_input.loc[len(df_input)] = [
            "calculate",
            "created_by_person_uuid",
            *list(empty.values()),
            *list(empty.values()),  # hint
            *list(empty.values()),  # help
            "",  # default
            "",  #'appearance', clean_name
            "",  #'constraint',
            *list(empty.values()),  #'constraint_message'
            "",  #'relevance'
            "",  #'disabled'
            "",  #'required'
            *list(empty.values()),  #'required message'
            "",  #'read only'
            "../inputs/user/contact_id",  #'expression'
            "",  #'repeat_count'
            "",  #'image'
            "",  # choice filter
        ]
        df_input.loc[len(df_input)] = [
            "calculate",
            "created_by_place_uuid_user",
            *list(empty.values()),
            *list(empty.values()),  # hint
            *list(empty.values()),  # help
            "",  # default
            "",  #'appearance', clean_name
            "",  #'constraint',
            *list(empty.values()),  #'constraint_message'
            "",  #'relevance'
            "",  #'disabled'
            "",  #'required'
            *list(empty.values()),  #'required message'
            "",  #'read only'
            "../inputs/user/facility_id",  #'expression'
            "",  #'repeat_count'
            "",  #'image'
            "",  # choice filter
        ]
        df_input.loc[len(df_input)] = [
            "calculate",
            "created_by",
            *list(empty.values()),
            *list(empty.values()),  # hint
            *list(empty.values()),  # help
            "",  # default
            "",  #'appearance', clean_name
            "",  #'constraint',
            *list(empty.values()),  #'constraint_message'
            "",  #'relevance'
            "",  #'disabled'
            "",  #'required'
            *list(empty.values()),  #'required message'
            "",  #'read only'
            "../inputs/user/name",  #'expression'
            "",  #'repeat_count'
            "",  #'image'
            "",  # choice filter
        ]
        df_input.loc[len(df_input)] = [
            "calculate",
            "created_by_place_uuid",
            *list(empty.values()),
            *list(empty.values()),  # hint
            *list(empty.values()),  # help
            "",  # default
            "",  #'appearance', clean_name
            "",  #'constraint',
            *list(empty.values()),  #'constraint_message'
            "",  #'relevance'
            "",  #'disabled'
            "",  #'required'
            *list(empty.values()),  #'required message'
            "",  #'read only'
            "../inputs/contact/_id",  #'expression'
            "",  #'repeat_count'
            "",  #'image'
            "",  # choice filter
        ]

        df_input.loc[len(df_input)] = [
            "calculate",
            "source_id",
            *list(empty.values()),
            *list(empty.values()),  # hint
            *list(empty.values()),  # help
            "",  # default
            "",  #'appearance', clean_name
            "",  #'constraint',
            *list(empty.values()),  #'constraint_message'
            "",  #'relevance'
            "",  #'disabled'
            "",  #'required'
            *list(empty.values()),  #'required message'
            "",  #'read only'
            "../inputs/source_id",  #'expression'
            "",  #'repeat_count'
            "",  #'image'
            "",  # choice filter
        ]
        df_input.loc[len(df_input)] = [
            "calculate",
            "patient_uuid",
            *list(empty.values()),
            *list(empty.values()),  # hint
            *list(empty.values()),  # help
            "",  # default
            "",  #'appearance', clean_name
            "",  #'constraint',
            *list(empty.values()),  #'constraint_message'
            "",  #'relevance'
            "",  #'disabled'
            "",  #'required'
            *list(empty.values()),  #'required message'
            "",  #'read only'
            "../inputs/user/facility_id",  #'expression'
            "",  #'repeat_count'
            "",  #'image'
            "",  # choice filter
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
        ]

        for input in inputs:
            df_input.loc[len(df_input)] = get_input_calc_line(input)

        return df_input

    def get_contact_inputs(self, df_input):
        empty = langs.get_trads("", force_dict=True)
        if not len(df_input[df_input['name'] == 'sex']):
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
            ]
        if not len(df_input[df_input['name'] == 'date_of_birth']):
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
        ]

        return df_input

    def get_cht_summary(self):
        df_summary = pd.DataFrame(columns=SURVEY_MAP.keys())
        # [ #type, '',#name ''#label, '',#hint '',#help '',#default '',#'appearance',  '',#'constraint',  '',#'constraint_message' '',#'relevance' '',#'disabled' '',#'required' '',#'required message' '',#'read only' '',#'expression' '',#'repeat_count' ''#'image' ],
        # df_summary.loc[len(df_summary)] = [ 'begin group', 'group_summary' , 'Summary',                                  '', '', '',  'field-list summary',  '', '', '', '', '', '', '', '', '', '' ]
        # df_summary.loc[len(df_summary)] = [ 'note',        'r_patient_info', '**${patient_name}** ID: ${patient_id}',  '', '', '',  '',                    '', '', '', '', '', '', '', '', '', '' ]
        # df_summary.loc[len(df_summary)] = [ 'note',        'r_followup', 'Follow Up <i class=“fa fa-flag”></i>', '', '', '',  '',  '', '','', '', '', '', '', '', '', '' ]
        # df_summary.loc[len(df_summary)] = [ 'note',        'r_followup_note' ,'FOLLOWUP instruction', '', '', '',  '',  '', '', '','', '', '', '', '', '', '' ]
        # df_summary.loc[len(df_summary)] = [ 'end group', '' ,'', '', '', '',  '',  '', '', '', '', '', '', '', '','', '' ]
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
                index = get_last_prev_index(df, e, depth + 1)
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

        settings = {
            "form_title": title,
            "form_id": form_id,
            "version": version,
            "default_language": "English (en)",
            "style": "pages",
        }
        df_settings = pd.DataFrame(settings, index=indx)
        df_settings.head()
        if len(self.df_survey[self.df_survey["name"] == "version"]):
            self.df_survey.loc[self.df_survey["name"] == "version", "label"] = (
                f"v{version}"
            )
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
                    lambda x: issubclass(x.__class__, TriccNodeEnd)
                    and getattr(x, "process", "") == "pause",
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
                    logger.critical(
                        f"impossible to get last index before pause: {e.get_name()}"
                    )
            forms = [form_id]
            for i, e in ends_prev:
                new_form_id = f"{form_id}_{clean_name(e.name)}"
                newfilename = f"{new_form_id}.xlsx"
                newpath = os.path.join(self.output_path, newfilename)
                settings = {
                    "form_title": title,
                    "form_id": f"{new_form_id}",
                    "version": version,
                    "default_language": "English (en)",
                    "style": "pages",
                }
                df_settings = pd.DataFrame(settings, index=indx)
                df_settings.head()
                task_df, hidden_names = make_breakpoints(
                    self.df_survey, i, e.name, replace_dots=True
                )
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
            if os.path.isdir(
                media_path
            ):  # check if it exists, because if it does, error will be raised
                shutil.rmtree(media_path)
                # (later change to make folder complaint to CHT)
            os.mkdir(media_path)

            file_names = os.listdir(media_path_tmp)
            for file_name in file_names:
                shutil.move(os.path.join(media_path_tmp, file_name), media_path)
            shutil.rmtree(media_path_tmp)

    def tricc_operation_zscore(self, ref_expressions):
        y, ll, m, s = self.get_zscore_params(ref_expressions)
        #  return ((Math.pow((y / m), l) - 1) / (s * l));
        return f"cht:extension-lib('{ref_expressions[0][1:-1]}.js',{self.clean_coalesce(ref_expressions[1])} ,{self.clean_coalesce(ref_expressions[2])} ,{self.clean_coalesce(ref_expressions[3])})"

    def tricc_operation_izscore(self, ref_expressions):
        z, ll, m, s = self.get_zscore_params(ref_expressions)
        #  return  (m * (z*s*l-1)^(1/l));
        return f"cht:extension-lib('{ref_expressions[0][1:-1]}.js',{self.clean_coalesce(ref_expressions[1])} ,{self.clean_coalesce(ref_expressions[2])} ,{self.clean_coalesce(ref_expressions[3])}, true)"

    def tricc_operation_drug_dosage(self, ref_expressions):
        # drug name
        # age
        # weight
        return f"cht:extension-lib('drugs.js',{','.join(map(self.clean_coalesce, ref_expressions))})"

