"""Registry of WHO XForY LMS tables for CDSS zscore secondary instances."""

from __future__ import annotations

import json
import logging
from functools import lru_cache
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Set

from tricc_oo.data.anthro.ranges import merge_sex_ranges

logger = logging.getLogger("default")

_ANTHRO_DIR = Path(__file__).resolve().parent

# Upper bound for last WFA age bin (days). WHO table ends at 1847 days (~5y).
_WFA_LAST_Y_MAX = 1855.0


def normalize_table_id(raw: Any) -> str:
    """Normalize a table id from expression operands (quotes/whitespace)."""
    if raw is None:
        return ""
    s = str(raw).strip()
    if (s.startswith("'") and s.endswith("'")) or (s.startswith('"') and s.endswith('"')):
        s = s[1:-1]
    return s.strip().lower()


def _load_json_table(filename: str) -> Dict[str, Any]:
    path = _ANTHRO_DIR / filename
    with path.open("r", encoding="utf-8") as fh:
        return json.load(fh)


@lru_cache(maxsize=16)
def _load_wfa_rows() -> tuple:
    data = _load_json_table("wfa.json")
    rows = merge_sex_ranges(
        data["male"],
        data["female"],
        list_name="wfa",
        last_y_max=_WFA_LAST_Y_MAX,
    )
    return tuple(rows)


# Map table id → loader returning list of choice-oriented dicts.
_LOADERS: Dict[str, Callable[[], List[Dict[str, Any]]]] = {
    "wfa": lambda: list(_load_wfa_rows()),
    # Future: wfl, wfh, lfa, bfa, acfa, hcfa, …
}


def get_supported_tables() -> Set[str]:
    return set(_LOADERS.keys())


def is_supported_table(table_id: Any) -> bool:
    return normalize_table_id(table_id) in _LOADERS


def get_choice_rows(table_id: Any) -> List[Dict[str, Any]]:
    """Return LMS choice rows for ``table_id`` (with y_min/y_max/sex/l/m/s).

    Raises:
        ValueError: if the table is not registered.
    """
    tid = normalize_table_id(table_id)
    loader = _LOADERS.get(tid)
    if loader is None:
        supported = ", ".join(sorted(_LOADERS)) or "(none)"
        raise ValueError(f"Unknown zscore table '{table_id}'. Supported: {supported}")
    rows = loader()
    # Ensure list_name is set for export
    for r in rows:
        r.setdefault("list_name", tid)
    return rows
