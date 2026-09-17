"""Render a ``TriccOperation`` tree as JavaScript for CHT ``context.expression``."""

from __future__ import annotations

import json
from typing import Any, List, Union

from tricc_oo.models.base import TriccOperation, TriccReference, TriccStatic


class ChtJsExpressionRenderer:
    """``TriccOperation`` → JavaScript over ``contact`` (CHT ``properties.json``)."""

    def render(self, operation: Any) -> str:
        if isinstance(operation, TriccOperation):
            args = [self.render(r) for r in (operation.reference or [])]
            method = getattr(self, f"tricc_operation_{operation.operator}", None)
            if method is None:
                raise NotImplementedError(
                    f"operator '{operation.operator}' is not supported in a CHT context.expression"
                )
            return method(args)
        return self.operand(operation)

    def operand(self, value: Any) -> str:
        if isinstance(value, TriccReference):
            name = str(value.value).strip()
            if not name:
                raise NotImplementedError("empty reference is not supported in a CHT context.expression")
            return f"contact.{name}"
        if isinstance(value, TriccStatic):
            return self._literal(value.value)
        if isinstance(value, (str, int, float, bool)) or value is None:
            return self._literal(value)
        raise NotImplementedError(
            f"operand {type(value).__name__} is not supported in a CHT context.expression"
        )

    def _literal(self, value: Any) -> str:
        if isinstance(value, bool):
            return "true" if value else "false"
        if value is None:
            return "null"
        if isinstance(value, (int, float)) and not isinstance(value, bool):
            if isinstance(value, float) and value.is_integer():
                return str(int(value))
            return json.dumps(value)
        return json.dumps(str(value))

    def tricc_operation_parenthesis(self, args: List[str]) -> str:
        inner = args[0] if args else "true"
        return f"({inner})"

    def tricc_operation_and(self, args: List[str]) -> str:
        if not args:
            return "true"
        if len(args) == 1:
            return args[0]
        return " && ".join(f"({a})" for a in args)

    def tricc_operation_or(self, args: List[str]) -> str:
        if not args:
            return "false"
        if len(args) == 1:
            return args[0]
        return " || ".join(f"({a})" for a in args)

    def tricc_operation_not(self, args: List[str]) -> str:
        return f"!({args[0]})"

    def tricc_operation_equal(self, args: List[str]) -> str:
        return f"{args[0]} === {args[1]}"

    def tricc_operation_not_equal(self, args: List[str]) -> str:
        return f"{args[0]} !== {args[1]}"

    def tricc_operation_less(self, args: List[str]) -> str:
        return f"{args[0]} < {args[1]}"

    def tricc_operation_more(self, args: List[str]) -> str:
        return f"{args[0]} > {args[1]}"

    def tricc_operation_less_or_equal(self, args: List[str]) -> str:
        return f"{args[0]} <= {args[1]}"

    def tricc_operation_more_or_equal(self, args: List[str]) -> str:
        return f"{args[0]} >= {args[1]}"

    def tricc_operation_istrue(self, args: List[str]) -> str:
        return f"{args[0]} === true || {args[0]} === 'true'"

    def tricc_operation_isfalse(self, args: List[str]) -> str:
        return f"{args[0]} === false || {args[0]} === 'false'"

    def tricc_operation_age_month(self, args: List[str]) -> str:
        return "ageInMonths(contact)"

    def tricc_operation_age_year(self, args: List[str]) -> str:
        return "ageInYears(contact)"

    def tricc_operation_age_day(self, args: List[str]) -> str:
        return "ageInDays(contact)"


def render_cht_js_expression(operation: Union[TriccOperation, TriccStatic, TriccReference]) -> str:
    return ChtJsExpressionRenderer().render(operation)
