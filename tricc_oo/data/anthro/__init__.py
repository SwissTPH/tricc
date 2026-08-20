"""WHO anthropometric LMS tables for CDSS zscore / izscore secondary instances."""

from tricc_oo.data.anthro.registry import (
    get_choice_rows,
    get_supported_tables,
    is_supported_table,
    normalize_table_id,
)

__all__ = [
    "get_choice_rows",
    "get_supported_tables",
    "is_supported_table",
    "normalize_table_id",
]
