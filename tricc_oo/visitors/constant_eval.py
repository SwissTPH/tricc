"""Build-time evaluation of constant expressions (RFC SwissTPH/tricc#86).

``evaluate_constant`` gives the value of an expression that uses no collected data: literals,
operators over them, and calculates that are constant in turn. It answers in three ways:

- a value (a ``TriccStatic``, or None for a CQL null);
- ``TriccNotConstant``: the expression reads collected data (an input, a select, an unknown
  name, stored data, ``Today()`` / ``Now()``, a function declared ``@retrieve: true``). The
  caller keeps it dynamic, silently;
- ``TriccEvalUnsupported``: the expression reads no collected data but uses an operator the
  table below cannot evaluate, or a function the build has no implementation of (declared
  ``@retrieve: false``, or not declared at all). The caller keeps it dynamic, with a warning.

A function called as written (a ``native`` operation) is looked up with ``functions(name)``:
its declaration in the project's CQL libraries (``converters/cql_library.FunctionSignature``),
whose ``@retrieve`` tag says whether it reads recorded data.

The whole expression is checked for collected data before any operator is evaluated, so an
unsupported operator only fails an expression that would otherwise be constant.

Semantics follow CQL: ``and`` / ``or`` / ``not`` are three-valued (None is null), any other
operator gives null for a null operand, division by zero is null, and numbers are ``Decimal``
(``Integer / Integer`` is a ``Decimal``). A result is given back as ``int`` when it is whole,
else ``float``, the way ``render_value`` writes numbers.
"""

from __future__ import annotations

from decimal import ROUND_FLOOR, Decimal, InvalidOperation
from typing import Any, Callable, Dict, List, Optional, Set

from tricc_oo.models.base import TriccOperation, TriccOperator, TriccReference, TriccStatic

#: ``resolve(name)``: the expression of the calculate called ``name`` (CQL text or parsed), or
#: None when ``name`` is not a calculate whose value can be known at build time
Resolver = Callable[[str], Any]
#: ``functions(name)``: the project's declaration of a function (a ``FunctionSignature``, with
#: its ``retrieve`` flag), or None when it declares none
Functions = Callable[[str], Any]


class TriccNotConstant(Exception):
    """The expression reads collected data: keep it dynamic."""


class TriccEvalUnsupported(Exception):
    """A constant expression uses an operator the build cannot evaluate.

    Attributes:
        operator: The operator (a ``TriccOperator`` value), for the error message.
    """

    def __init__(self, operator: Any, detail: str = ""):
        self.operator = str(operator)
        super().__init__(f"{self.operator}{': ' + detail if detail else ''}")


#: operators whose value depends on the moment
_NEVER_CONSTANT = {TriccOperator.TODAY, TriccOperator.NOW}

_UNSET = object()


def evaluate_constant(
    expression: Any, resolve: Optional[Resolver] = None, functions: Optional[Functions] = None
) -> Optional[TriccStatic]:
    """The value of a constant expression.

    Args:
        expression: CQL text, or a parsed expression (``TriccStatic``, ``TriccReference``,
            ``TriccOperation``).
        resolve: Gives the expression of a calculate by name (see ``Resolver``). None: every
            reference is collected data.
        functions: Gives a function's declaration by name (see ``Functions``). None: no
            function is declared.

    Returns:
        The value as a ``TriccStatic``, or None when the expression is a CQL null.

    Raises:
        TriccNotConstant: The expression reads collected data, or is not CQL.
        TriccEvalUnsupported: The expression reads no collected data but uses an operator
            outside the table or a function the build cannot run, or applies an operator to
            values of the wrong types.
    """
    value = _Evaluator(resolve, functions).run(expression)
    return None if value is None else TriccStatic(value=_out(value))


class _Evaluator:
    def __init__(self, resolve: Optional[Resolver], functions: Optional[Functions]):
        self.resolve = resolve
        self.functions = functions
        self.parsed: Dict[str, Any] = {}  # calculate name -> parsed expression
        self.checked: Set[str] = set()  # calculates known to read no collected data
        self.values: Dict[str, Any] = {}  # calculate name -> value

    def run(self, expression: Any) -> Any:
        parsed = _parse(expression)
        self.check(parsed, [])
        return self.eval(parsed)

    # -- pass 1: does it read collected data? --------------------------------
    def calculate(self, name: str) -> Any:
        if name not in self.parsed:
            source = self.resolve(name) if self.resolve else None
            if source is None:
                raise TriccNotConstant(f"{name!r} is not a constant calculate")
            self.parsed[name] = _parse(source)
        return self.parsed[name]

    def check(self, item: Any, stack: List[str]) -> None:
        if item is None or isinstance(item, TriccStatic) and _is_plain(item.value):
            return
        if isinstance(item, list):
            for sub in item:
                self.check(sub, stack)
            return
        if isinstance(item, TriccReference):
            name = item.value
            if name in self.checked:
                return
            if name in stack:
                raise TriccNotConstant(f"cycle through {' > '.join(stack + [name])}")
            self.check(self.calculate(name), stack + [name])
            self.checked.add(name)
            return
        if isinstance(item, TriccOperation):
            if item.retrieves_stored_data or item.operator in _NEVER_CONSTANT:
                raise TriccNotConstant(f"{item.operator} is not constant")
            refs = list(item.reference or [])
            if item.operator == TriccOperator.NATIVE:
                name = refs.pop(0) if refs else None
                signature = self.functions(name) if self.functions and isinstance(name, str) else None
                if signature is not None and signature.retrieve:
                    raise TriccNotConstant(f"{name} reads recorded data (@retrieve: true)")
            for sub in refs:
                self.check(sub, stack)
            return
        # a node used as a value, an Expression, anything else: data
        raise TriccNotConstant(f"{item!r} is not a value")

    # -- pass 2: evaluate ------------------------------------------------------
    def eval(self, item: Any) -> Any:
        if item is None:
            return None
        if isinstance(item, TriccStatic):
            return _in(item.value)
        if isinstance(item, TriccReference):
            name = item.value
            if name not in self.values:
                self.values[name] = self.eval(self.parsed[name])
            return self.values[name]
        operator = item.operator
        refs = list(item.reference or [])
        if operator == TriccOperator.NATIVE:
            name = refs[0] if refs else "?"
            declared = self.functions(name) if self.functions and isinstance(name, str) else None
            why = ("declared @retrieve: false, but the build has no implementation of it" if declared
                   else "not declared in the project's CQL libraries")
            raise TriccEvalUnsupported(name, why)
        lazy = _LAZY.get(operator)
        if lazy is not None:
            return lazy(self, refs)
        function = _TABLE.get(operator)
        if function is None:
            raise TriccEvalUnsupported(operator)
        args = [self.eval(r) for r in refs]
        try:
            return function(*args)
        except TriccEvalUnsupported:
            raise
        except (TypeError, ValueError, InvalidOperation) as error:
            raise TriccEvalUnsupported(operator, f"{args!r}: {error}") from None


def _parse(expression: Any) -> Any:
    if not isinstance(expression, str):
        return expression
    from tricc_oo.converters.cql_to_operation import transform_cql_to_operation

    try:
        parsed = transform_cql_to_operation(expression, quiet=True)
    except Exception:
        raise TriccNotConstant(f"{expression!r} is not CQL") from None
    if parsed is None and expression.strip() != "null":
        raise TriccNotConstant(f"{expression!r} is not CQL")
    return parsed


def _is_plain(value: Any) -> bool:
    return isinstance(value, (str, int, float, bool))


def _in(value: Any) -> Any:
    """A literal as the evaluator holds it: numbers as ``Decimal``."""
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return value
    return Decimal(str(value))


def _out(value: Any) -> Any:
    """A value back for ``TriccStatic``: a whole ``Decimal`` as ``int``, else ``float``."""
    if isinstance(value, Decimal):
        return int(value) if value == value.to_integral_value() else float(value)
    return value


# ---------------------------------------------------------------------------
# Operator table
# ---------------------------------------------------------------------------


def _kind(value: Any) -> str:
    if isinstance(value, bool):
        return "boolean"
    if isinstance(value, Decimal):
        return "number"
    return type(value).__name__


def _same_kind(operator, *values) -> None:
    kinds = {_kind(v) for v in values}
    if len(kinds) > 1:
        raise TriccEvalUnsupported(operator, f"compares {' and '.join(sorted(kinds))}")


def _numbers(operator, *values) -> None:
    if any(_kind(v) != "number" for v in values):
        raise TriccEvalUnsupported(operator, f"needs numbers, got {values!r}")


def _nullable(function):
    """Null when any operand is null."""

    def wrapped(*args):
        return None if any(a is None for a in args) else function(*args)

    return wrapped


def _compare(operator, test):
    def compare(left, right):
        _same_kind(operator, left, right)
        return test(left, right)

    return _nullable(compare)


def _plus(*args):
    if len(args) == 1:
        _numbers(TriccOperator.PLUS, *args)
        return args[0]
    left, right = args
    if isinstance(left, str) and isinstance(right, str):
        return left + right
    _numbers(TriccOperator.PLUS, left, right)
    return left + right


def _minus(*args):
    _numbers(TriccOperator.MINUS, *args)
    return -args[0] if len(args) == 1 else args[0] - args[1]


def _multiplied(left, right):
    _numbers(TriccOperator.MULTIPLIED, left, right)
    return left * right


def _divided(left, right):
    _numbers(TriccOperator.DIVIDED, left, right)
    return None if right == 0 else left / right


def _modulo(left, right):
    _numbers(TriccOperator.MODULO, left, right)
    return None if right == 0 else left % right


def _round(value, precision=Decimal(0)):
    """CQL ``Round``: halves go toward positive infinity (``Round(-1.5)`` is ``-1``)."""
    _numbers(TriccOperator.ROUND, value, precision)
    step = Decimal(1).scaleb(-int(precision))
    return ((value / step) + Decimal("0.5")).quantize(Decimal(1), rounding=ROUND_FLOOR) * step


def _abs(value):
    _numbers(TriccOperator.ABS, value)
    return abs(value)


def _extreme(operator, pick):
    def extreme(*args):
        _same_kind(operator, *args)
        return pick(args)

    return _nullable(extreme)


def _concatenate(*args):
    if any(not isinstance(a, str) for a in args):
        raise TriccEvalUnsupported(TriccOperator.CONCATENATE, f"needs texts, got {args!r}")
    return "".join(args)


def _boolean(operator, value):
    if value is not None and not isinstance(value, bool):
        raise TriccEvalUnsupported(operator, f"needs a boolean, got {value!r}")
    return value


def _and(self: _Evaluator, refs) -> Optional[bool]:
    null = False
    for ref in refs:
        value = _boolean(TriccOperator.AND, self.eval(ref))
        if value is False:
            return False
        null = null or value is None
    return None if null else True


def _or(self: _Evaluator, refs) -> Optional[bool]:
    null = False
    for ref in refs:
        value = _boolean(TriccOperator.OR, self.eval(ref))
        if value is True:
            return True
        null = null or value is None
    return None if null else False


def _if(self: _Evaluator, refs) -> Any:
    condition = _boolean(TriccOperator.IF, self.eval(refs[0]))
    if condition is True:
        return self.eval(refs[1])
    return self.eval(refs[2]) if len(refs) > 2 else None


def _coalesce(self: _Evaluator, refs) -> Any:
    for ref in refs:
        value = self.eval(ref)
        if value is not None:
            return value
    return None


def _not(value):
    return None if value is None else not _boolean(TriccOperator.NOT, value)


#: operators that evaluate their operands themselves (short circuit, branches)
_LAZY: Dict[TriccOperator, Callable[[_Evaluator, list], Any]] = {
    TriccOperator.AND: _and,
    TriccOperator.OR: _or,
    TriccOperator.IF: _if,
    TriccOperator.COALESCE: _coalesce,
}

#: operators over evaluated operands
_TABLE: Dict[TriccOperator, Callable[..., Any]] = {
    TriccOperator.PARENTHESIS: lambda value: value,
    TriccOperator.NOT: _not,
    TriccOperator.EQUAL: _compare(TriccOperator.EQUAL, lambda a, b: a == b),
    TriccOperator.NOTEQUAL: _compare(TriccOperator.NOTEQUAL, lambda a, b: a != b),
    TriccOperator.MORE: _compare(TriccOperator.MORE, lambda a, b: a > b),
    TriccOperator.LESS: _compare(TriccOperator.LESS, lambda a, b: a < b),
    TriccOperator.MORE_OR_EQUAL: _compare(TriccOperator.MORE_OR_EQUAL, lambda a, b: a >= b),
    TriccOperator.LESS_OR_EQUAL: _compare(TriccOperator.LESS_OR_EQUAL, lambda a, b: a <= b),
    TriccOperator.PLUS: _nullable(_plus),
    TriccOperator.MINUS: _nullable(_minus),
    TriccOperator.MULTIPLIED: _nullable(_multiplied),
    TriccOperator.DIVIDED: _nullable(_divided),
    TriccOperator.MODULO: _nullable(_modulo),
    TriccOperator.ROUND: _nullable(_round),
    TriccOperator.ABS: _nullable(_abs),
    TriccOperator.MIN: _extreme(TriccOperator.MIN, min),
    TriccOperator.MAX: _extreme(TriccOperator.MAX, max),
    TriccOperator.CONCATENATE: _nullable(_concatenate),
    TriccOperator.ISTRUE: lambda value: value is True,
    TriccOperator.ISFALSE: lambda value: value is False,
    TriccOperator.ISNOTTRUE: lambda value: value is not True,
    TriccOperator.ISNOTFALSE: lambda value: value is not False,
    TriccOperator.EXISTS: lambda value: value is not None,
    TriccOperator.NOTEXISTS: lambda value: value is None,
    TriccOperator.ISNULL: lambda value: value is None,
    TriccOperator.ISNOTNULL: lambda value: value is not None,
}

SUPPORTED_OPERATORS = frozenset(_TABLE) | frozenset(_LAZY)
