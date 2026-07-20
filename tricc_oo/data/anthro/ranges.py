"""Convert discrete WHO LMS points into half-open y_min / y_max bins."""

from typing import Any, Dict, Iterable, List, Optional, Sequence


def points_to_ranges(
    points: Sequence[Dict[str, Any]],
    *,
    sex: str,
    last_y_max: Optional[float] = None,
    list_name: str = "",
) -> List[Dict[str, Any]]:
    """Expand discrete LMS points into non-overlapping ``[y_min, y_max)`` rows.

    Each WHO table point is ``{y, l, s, m}`` (``y`` = independent axis: age days,
    length cm, …). Consecutive points define half-open bins so continuous
    ``x`` matches exactly one row via ``y_min <= x and y_max > x``.

    Args:
        points: LMS points sorted or unsorted by ``y``.
        sex: Sex label stored on each row (``male`` / ``female``).
        last_y_max: Upper bound for the final bin. Defaults to last ``y`` +
            previous bin width (or ``last_y + 1`` when only one point).
        list_name: Optional table id for unique ``value`` prefixes.

    Returns:
        Choice-oriented dicts with ``sex``, ``y_min``, ``y_max``, ``l``, ``m``,
        ``s``, and ``value``.
    """
    if not points:
        return []

    ordered = sorted(points, key=lambda p: float(p["y"]))
    rows: List[Dict[str, Any]] = []
    prefix = f"{list_name}_" if list_name else ""
    sex_prefix = "m" if sex.lower().startswith("m") else "f"

    for i, pt in enumerate(ordered):
        y_min = float(pt["y"])
        if i + 1 < len(ordered):
            y_max = float(ordered[i + 1]["y"])
        elif last_y_max is not None:
            y_max = float(last_y_max)
        elif i > 0:
            prev_width = y_min - float(ordered[i - 1]["y"])
            y_max = y_min + (prev_width if prev_width > 0 else 1.0)
        else:
            y_max = y_min + 1.0

        if y_max <= y_min:
            y_max = y_min + 1.0

        y_key = str(int(y_min)) if y_min == int(y_min) else str(y_min).replace(".", "_")
        rows.append(
            {
                "value": f"{prefix}{sex_prefix}_{y_key}",
                "label": f"{prefix}{sex_prefix}_{y_key}",
                "sex": sex,
                "y_min": y_min,
                "y_max": y_max,
                "l": float(pt["l"]),
                "m": float(pt["m"]),
                "s": float(pt["s"]),
            }
        )
    return rows


def merge_sex_ranges(
    male: Iterable[Dict[str, Any]],
    female: Iterable[Dict[str, Any]],
    *,
    list_name: str,
    last_y_max: Optional[float] = None,
) -> List[Dict[str, Any]]:
    """Build choice rows for both sexes under one list_name."""
    rows: List[Dict[str, Any]] = []
    rows.extend(
        points_to_ranges(list(male), sex="male", list_name=list_name, last_y_max=last_y_max)
    )
    rows.extend(
        points_to_ranges(list(female), sex="female", list_name=list_name, last_y_max=last_y_max)
    )
    return rows
