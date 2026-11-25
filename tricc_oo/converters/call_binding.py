"""Bind the arguments of a call to its parameters (feature/20261125-calculate-functions.md §2.1).

Shared by the calculate functions (``IsAdult(age, declared)``) and the decision table calls
(``DMN(table, …)``, aliases): positional arguments first, then a trailing ``Tuple{ name: value }``
by name. Each parameter ends up with one of:

- a passed value (an expression, a reference or a literal);
- :data:`NULL`, an explicit ``null`` (no value, nothing is looked up for it);
- :data:`MISSING`, left out: bound at instantiation from its fallbacks (§2.3).

The binding errors have the same codes for both kinds of call: ``E_CALL_ARG_UNKNOWN``,
``E_CALL_ARG_TWICE``, ``E_CALL_ARITY``.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, List, Optional, Sequence, Tuple, Type

from tricc_oo.models.base import TriccOperation, TriccOperator

E_CALL_ARG_UNKNOWN = "E_CALL_ARG_UNKNOWN"
E_CALL_ARG_TWICE = "E_CALL_ARG_TWICE"
E_CALL_ARITY = "E_CALL_ARITY"


class _Sentinel:
    def __init__(self, name: str):
        self.name = name

    def __repr__(self) -> str:
        return self.name


#: an argument bound to ``null``: no value, no fallback
NULL = _Sentinel("NULL")
#: a parameter the call leaves out: bound from its fallbacks at instantiation
MISSING = _Sentinel("MISSING")


class CallError(ValueError):
    """A call that cannot be bound or exported.

    Attributes:
        code: The error code (``E_CALL_ARITY``, ``E_FUNCTION_UNKNOWN``, …).
        message: The message without the code.
    """

    def __init__(self, code: str, message: str):
        super().__init__(f"{code}: {message}")
        self.code = code
        self.message = message


@dataclass(frozen=True)
class CallParam:
    """A parameter of a function, or an input of a decision table.

    Attributes:
        name: The parameter name (``age``).
        type: Its type as written (``Integer``, ``decimal``), if known.
        fallback: The concept whose latest value a left-out argument takes (§2.3 step 1).
        retrievals: The retrieval codes (``#age_years``) allowed for a left-out argument, in
            order (§2.3 step 3).
    """

    name: str
    type: Optional[str] = None
    fallback: Optional[str] = None
    retrievals: Tuple[str, ...] = field(default_factory=tuple)


def is_named_arguments(arg: Any) -> bool:
    """Whether ``arg`` is a ``Tuple{…}`` of named arguments."""
    return isinstance(arg, TriccOperation) and arg.operator == TriccOperator.TUPLE


def split_named(args: Sequence[Any]) -> Tuple[List[Any], List[Tuple[str, Any]]]:
    """Split a call's arguments into the positional ones and the trailing ``Tuple{…}``.

    Args:
        args: The arguments as parsed.

    Returns:
        ``(positional, [(name, value)])``.
    """
    args = list(args)
    if args and is_named_arguments(args[-1]):
        flat = list(args[-1].reference or [])
        named = [(str(getattr(flat[i], "value", flat[i])), flat[i + 1]) for i in range(0, len(flat) - 1, 2)]
        return args[:-1], named
    return args, []


def _index(params: Sequence[str], key: str) -> Optional[int]:
    for i, name in enumerate(params):
        if name == key:
            return i
    lowered = key.lower()
    for i, name in enumerate(params):
        if name.lower() == lowered:
            return i
    return None


def bind_arguments(
    call: str,
    params: Sequence[str],
    positional: Sequence[Any],
    named: Sequence[Tuple[str, str, Any]] = (),
    error: Type[CallError] = CallError,
    owner: str = "",
) -> List[Any]:
    """One value per parameter: the passed value, :data:`NULL` or :data:`MISSING`.

    Args:
        call: The function name, for messages.
        params: The parameter names, in order.
        positional: The positional arguments.
        named: ``(code when the name is unknown, name, value)`` per named argument.
        error: The exception class to raise (``DecisionTableError`` for a table call).
        owner: What the parameters belong to, for messages (``table 'diazepam'``).

    Raises:
        CallError: ``E_CALL_ARITY`` (too many positional arguments), the given code for an
            unknown name, ``E_CALL_ARG_TWICE`` for a parameter given twice.
    """
    where = f" of {owner}" if owner else ""
    if len(positional) > len(params):
        raise error(
            E_CALL_ARITY,
            f"{call}: {owner or call} has {len(params)} parameters ({', '.join(params)}); "
            f"got {len(positional)} arguments.",
        )
    values: List[Any] = [MISSING] * len(params)
    for i, value in enumerate(positional):
        values[i] = NULL if value is None else value
    for code, key, value in named:
        at = _index(params, key)
        if at is None:
            raise error(code, f"{call}: {owner or call} has no parameter {key!r}.")
        if values[at] is not MISSING:
            raise error(E_CALL_ARG_TWICE, f"{call}: parameter {key!r}{where} is given twice.")
        values[at] = NULL if value is None else value
    return values
