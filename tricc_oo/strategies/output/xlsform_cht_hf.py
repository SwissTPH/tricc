import logging

import pandas as pd

from tricc_oo.models.lang import SingletonLangClass
from tricc_oo.serializers.xls_form import (
    SURVEY_MAP,
)
from tricc_oo.strategies.output.xlsform_cht import XLSFormCHTStrategy

langs = SingletonLangClass()
logger = logging.getLogger("default")


class XLSFormCHTHFStrategy(XLSFormCHTStrategy):

    def get_contact_inputs(self, df_inputs):
        return None

    def get_contact_inputs_calculate(self, df_inputs):
        return None

    def get_cht_summary(self):

        df_summary = pd.DataFrame(columns=SURVEY_MAP.keys())
        return df_summary

    def tricc_operation_age_day(self, exps):
        raise NotImplementedError("AgeInDays Not compatible with this strategy")

    def tricc_operation_age_year(self, exps):
        raise NotImplementedError("AgeInYears Not compatible with this strategy")

    def tricc_operation_age_month(self, exps):
        raise NotImplementedError("AgeInMonths Not compatible with this strategy")
