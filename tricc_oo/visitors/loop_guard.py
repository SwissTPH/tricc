"""Runtime guards that turn silent hangs into a loud failure with a stack trace.

Two shapes of runaway work show up when converting large draw.io projects:

* a ``while`` loop that never drains its work list (``stashed_node_func``), and
* recursion that re-expands the same sub-graph over and over
  (``get_node_expression`` -> ``get_prev_node_expression`` ->
  ``get_calculation_terms`` -> ``get_node_expression`` ...).

Neither raises on its own: the loop keeps spinning and the recursion stays under
Python's recursion limit while doing exponential work, so a conversion just never
finishes. The guards here give every such loop a budget. When the budget is
exhausted they log the offending path, the repeated nodes on it and the Python
stack, then raise :class:`TriccLoopError` instead of spinning forever.

Budgets are tunable through the environment so a genuinely huge (but healthy)
project can be pushed through without patching code:

===================================  =========================================
``TRICC_MAX_LOOP_ITERATIONS``        iterations allowed in a guarded while loop
``TRICC_MAX_EXPRESSION_CALLS``       guarded recursive calls per top-level entry
``TRICC_MAX_EXPRESSION_DEPTH``       nesting depth allowed in guarded recursion
``TRICC_LOOP_GUARD_PDB``            ``1`` to drop into ``pdb`` when a guard trips
===================================  =========================================
"""
import logging
import os
import traceback
from collections import Counter

logger = logging.getLogger("default")

# Healthy conversions of the reference projects (demo / etat / combacal) peak at ~130
# loop iterations, ~20 recursive expression calls per top-level entry and depth ~11.
# These budgets leave three orders of magnitude of headroom: they only exist to make a
# pathological graph fail fast instead of hanging.
DEFAULT_MAX_LOOP_ITERATIONS = 50_000
DEFAULT_MAX_EXPRESSION_CALLS = 20_000
DEFAULT_MAX_EXPRESSION_DEPTH = 100

# How many entries of the offending path to log on each side of the trip point.
PATH_LOG_LIMIT = 60


class TriccLoopError(RuntimeError):
    """Raised when a loop / recursion guard exhausts its budget."""


def _env_int(name, default):
    """Read a positive int budget from the environment, falling back to ``default``."""
    raw = os.environ.get(name)
    if not raw:
        return default
    try:
        value = int(raw)
    except ValueError:
        logger.warning(f"{name}={raw!r} is not an integer, using {default}")
        return default
    if value <= 0:
        logger.warning(f"{name}={value} must be positive, using {default}")
        return default
    return value


def describe_node(node):
    """Short, stable label for a node used in guard diagnostics."""
    if node is None:
        return "None"
    try:
        name = node.get_name() if hasattr(node, "get_name") else str(node)
    except Exception:  # a half-built node must not break the diagnostics
        name = repr(node)
    activity = getattr(node, "activity", None)
    if activity is not None and activity is not node:
        try:
            name = f"{activity.get_name()}:{getattr(activity, 'instance', '')}|{name}"
        except Exception:
            pass
    return f"{node.__class__.__name__}::{name}"


def trip(reason, context=None):
    """Log ``reason``, the guard ``context`` lines and the Python stack, then raise.

    Args:
        reason: one-line explanation of which budget was exhausted.
        context: optional iterable of extra diagnostic lines to log before the stack.

    Raises:
        TriccLoopError: always.
    """
    logger.critical(f"loop guard tripped: {reason}")
    for line in context or []:
        logger.critical(line)
    logger.critical("stack trace at the moment the guard tripped:\n" + "".join(traceback.format_stack()))
    if _env_int("TRICC_LOOP_GUARD_PDB", 0):
        logger.critical("TRICC_LOOP_GUARD_PDB set: entering pdb")
        import pdb

        pdb.set_trace()
    raise TriccLoopError(reason)


class LoopGuard:
    """Iteration budget for a ``while`` loop.

    Call :meth:`tick` once per iteration; the guard trips when the loop has run
    more than ``max_iterations`` times.

    Args:
        name: loop name, used in the failure message.
        max_iterations: budget override; defaults to ``TRICC_MAX_LOOP_ITERATIONS``.
    """

    def __init__(self, name, max_iterations=None):
        self.name = name
        self.max_iterations = max_iterations or _env_int("TRICC_MAX_LOOP_ITERATIONS", DEFAULT_MAX_LOOP_ITERATIONS)
        self.iterations = 0

    def tick(self, context=None):
        """Count one iteration and trip once the budget is exhausted.

        Args:
            context: optional callable or iterable providing diagnostic lines,
                evaluated only when the guard actually trips.
        """
        self.iterations += 1
        if self.iterations <= self.max_iterations:
            return
        lines = context() if callable(context) else context
        trip(
            f"{self.name} ran {self.iterations} iterations "
            f"(limit {self.max_iterations}, raise TRICC_MAX_LOOP_ITERATIONS to allow more)",
            lines,
        )


class RecursionGuard:
    """Call-count and depth budget for a recursive function.

    The guard is shared by every level of one recursion; it resets when the
    outermost call returns, so the budget applies per top-level entry.

    Args:
        name: function name, used in the failure message.
        max_calls: budget override; defaults to ``TRICC_MAX_EXPRESSION_CALLS``.
        max_depth: budget override; defaults to ``TRICC_MAX_EXPRESSION_DEPTH``.
        describe: turns a guarded target into a diagnostic label. Only called when
            the guard trips, so guarding a call stays cheap.
    """

    def __init__(self, name, max_calls=None, max_depth=None, describe=describe_node):
        self.name = name
        self.describe = describe
        self.max_calls = max_calls or _env_int("TRICC_MAX_EXPRESSION_CALLS", DEFAULT_MAX_EXPRESSION_CALLS)
        self.max_depth = max_depth or _env_int("TRICC_MAX_EXPRESSION_DEPTH", DEFAULT_MAX_EXPRESSION_DEPTH)
        self.path = []
        self.calls = 0

    def __call__(self, target):
        """Return a context manager guarding one recursive call on ``target``."""
        return _RecursionFrame(self, target)

    def _enter(self, target):
        self.path.append(target)
        self.calls += 1
        if len(self.path) > self.max_depth:
            self._trip(
                f"{self.name} recursed {len(self.path)} levels deep "
                f"(limit {self.max_depth}, raise TRICC_MAX_EXPRESSION_DEPTH to allow more)"
            )
        if self.calls > self.max_calls:
            self._trip(
                f"{self.name} made {self.calls} recursive calls "
                f"(limit {self.max_calls}, raise TRICC_MAX_EXPRESSION_CALLS to allow more)"
            )

    def _exit(self):
        if self.path:
            self.path.pop()
        if not self.path:
            # outermost call returned: the next top-level entry starts fresh
            self.calls = 0

    def _trip(self, reason):
        try:
            trip(reason, self._diagnostics())
        finally:
            # let the exception unwind without the aborted path leaking into the
            # next top-level call
            self.path = []
            self.calls = 0

    def _diagnostics(self):
        lines = [f"{self.name} path ({len(self.path)} levels, {self.calls} calls):"]
        path = [self.describe(target) for target in self.path]
        if len(path) > 2 * PATH_LOG_LIMIT:
            shown = (
                [(i, path[i]) for i in range(PATH_LOG_LIMIT)]
                + [(None, f"... {len(path) - 2 * PATH_LOG_LIMIT} levels omitted ...")]
                + [(i, path[i]) for i in range(len(path) - PATH_LOG_LIMIT, len(path))]
            )
        else:
            shown = list(enumerate(path))
        for index, label in shown:
            lines.append(f"  {label}" if index is None else f"  [{index}] {label}")
        repeated = [(label, count) for label, count in Counter(path).most_common(10) if count > 1]
        if repeated:
            lines.append("nodes revisited on that path (likely dependency loop):")
            for label, count in repeated:
                lines.append(f"  {count}x {label}")
        return lines


class _RecursionFrame:
    """One guarded level of a :class:`RecursionGuard` recursion."""

    __slots__ = ("guard", "target")

    def __init__(self, guard, target):
        self.guard = guard
        self.target = target

    def __enter__(self):
        self.guard._enter(self.target)
        return self.guard

    def __exit__(self, exc_type, exc, tb):
        self.guard._exit()
        return False
