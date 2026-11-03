"""Parse a small UCUM time subset into seconds for intervention ``start.due`` / ``window``."""

from __future__ import annotations

import math
import re
from typing import Dict, Optional, Union

UCUM_TIME_UNITS = ("s", "min", "h", "d", "wk", "mo")
SECONDS_PER_UNIT = {
    "s": 1,
    "min": 60,
    "h": 3600,
    "d": 86400,
    "wk": 7 * 86400,
    "mo": 30 * 86400,  # approximation, documented in the spec
}
_DURATION_RE = re.compile(r"^\s*([+-]?\d+(?:\.\d+)?)\s*([A-Za-z]+)\s*$")
FHIR_DURATION_SYSTEM = "http://unitsofmeasure.org"


def parse_duration(value: Union[str, int, float, None], field_name: str = "duration") -> int:
    """Return seconds for a UCUM time quantity (``3 d``, ``90 min``). Integers are seconds."""
    if value is None or value == "":
        raise ValueError(f"{field_name} is required")
    if isinstance(value, bool):
        raise ValueError(f"{field_name} must be a UCUM time quantity, e.g. '3 d'")
    if isinstance(value, (int, float)):
        seconds = int(value)
        if seconds < 0:
            raise ValueError(f"{field_name} must be >= 0 seconds")
        return seconds
    text = str(value).strip()
    match = _DURATION_RE.match(text)
    if not match:
        raise ValueError(
            f"{field_name} {text!r} is not a UCUM time quantity "
            f"(allowed units: {', '.join(UCUM_TIME_UNITS)})"
        )
    amount = float(match.group(1))
    unit = match.group(2)
    if unit not in SECONDS_PER_UNIT:
        raise ValueError(
            f"{field_name} unit {unit!r} is not allowed "
            f"(use one of: {', '.join(UCUM_TIME_UNITS)})"
        )
    if amount < 0:
        raise ValueError(f"{field_name} must be >= 0")
    return int(amount * SECONDS_PER_UNIT[unit])


def to_days(seconds: int, round_up: bool = True) -> int:
    """Convert seconds to whole days for CHT ``events.days`` / ``start`` / ``end``."""
    if seconds <= 0:
        return 0
    days = seconds / 86400
    return math.ceil(days) if round_up else int(days)


def to_fhir_duration(seconds: int) -> Dict[str, object]:
    """Pick the largest UCUM unit that divides ``seconds`` exactly; default to days."""
    if seconds < 0:
        raise ValueError("duration must be >= 0 seconds")
    for unit in ("mo", "wk", "d", "h", "min", "s"):
        size = SECONDS_PER_UNIT[unit]
        if seconds % size == 0:
            return {
                "value": seconds // size,
                "unit": unit,
                "system": FHIR_DURATION_SYSTEM,
                "code": unit,
            }
    return {
        "value": to_days(seconds, round_up=True),
        "unit": "d",
        "system": FHIR_DURATION_SYSTEM,
        "code": "d",
    }


def coerce_optional_duration(value: Union[str, int, float, None], field_name: str) -> Optional[int]:
    if value is None or value == "":
        return None
    return parse_duration(value, field_name)
