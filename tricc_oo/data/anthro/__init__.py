"""WHO anthropometric LMS tables, read by zscore / izscore as built-in decision tables."""

from tricc_oo.data.anthro.registry import (
    builtin_decision_table,
    get_choice_rows,
    get_supported_tables,
    is_supported_table,
    normalize_table_id,
)

__all__ = [
    "builtin_decision_table",
    "get_choice_rows",
    "get_supported_tables",
    "is_supported_table",
    "normalize_table_id",
]
