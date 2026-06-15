"""
Strategy system for TRICC.

Preferred way to obtain strategies:

    from tricc_oo.strategies.registry import get_input_strategy, get_output_strategy

    Strategy = get_input_strategy("YamlStrategy")   # by name
    Strategy = get_output_strategy(MyStrategyClass) # direct class (excellent for tests)
"""

from tricc_oo.strategies.registry import (
    register_input_strategy,
    register_output_strategy,
    get_input_strategy,
    get_output_strategy,
    list_input_strategies,
    list_output_strategies,
)

# Eagerly import the built-in strategies so their @register_* decorators run.
# This is the price of a simple decorator-based registry.
# External strategies can still register themselves at import time.
from tricc_oo.strategies.input.drawio import DrawioStrategy  # noqa: F401
from tricc_oo.strategies.input.yaml import YamlStrategy  # noqa: F401

from tricc_oo.strategies.output.xls_form import XLSFormStrategy  # noqa: F401
from tricc_oo.strategies.output.xlsform_cdss import XLSFormCDSSStrategy  # noqa: F401
from tricc_oo.strategies.output.xlsform_cht import XLSFormCHTStrategy  # noqa: F401
from tricc_oo.strategies.output.xlsform_cht_hf import XLSFormCHTHFStrategy  # noqa: F401
from tricc_oo.strategies.output.html_form import HTMLStrategy  # noqa: F401
from tricc_oo.strategies.output.dhis2_form import DHIS2Strategy  # noqa: F401
from tricc_oo.strategies.output.openmrs_form import OpenMRSStrategy  # noqa: F401
from tricc_oo.strategies.output.fhir_form import FHIRStrategy  # noqa: F401
from tricc_oo.strategies.output.opensrp import OpenSRPStrategy  # noqa: F401

__all__ = [
    "register_input_strategy",
    "register_output_strategy",
    "get_input_strategy",
    "get_output_strategy",
    "list_input_strategies",
    "list_output_strategies",
]