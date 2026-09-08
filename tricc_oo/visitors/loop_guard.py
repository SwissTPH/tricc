"""Runtime guards that turn silent hangs into a loud failure with a stack trace.

Two shapes of runaway work show up when converting large draw.io projects:

* a ``while`` loop that never drains its work list (``stashed_node_func``), and
* recursion that re-expands the same sub-graph over and over
  (``get_node_expression`` -> ``get_prev_node_expression`` ->
  ``get_calculation_terms`` -> ``get_node_expression`` ...).

Neither raises on its own: the loop keeps spinning and the recursion stays under
Python's recursion limit while doing exponential work, so a conversion just never
finishes. The guards here give every such loop a budget. When the budget is
exhausted they raise :class:`TriccLoopError` instead of spinning forever, after
logging

* the node the recursion looped on, and the segment that repeats around it,
* the path from the nearest branching node down to that loop -- the stretch of the
  drawing to look at,
* every node revisited on the path, most revisited first,
* the full expansion path (middle elided when deep) and the Python stack.

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

# How many entries of the offending path to log on each side of an elision.
PATH_LOG_LIMIT = 60
# Same, for the repeating segment of a detected loop (kept shorter: it repeats).
LOOP_SEGMENT_LOG_LIMIT = 20


def _node_edges(node, attribute):
    """``node.prev_nodes`` / ``node.next_nodes`` as a sized collection (never None)."""
    return getattr(node, attribute, None) or ()


def _is_branching(node):
    """True when the graph forks at ``node``.

    More than one predecessor (the direction expression expansion walks) or more than
    one next node: either way the node is a decision point an author can recognise in
    the drawing.
    """
    return len(_node_edges(node, "prev_nodes")) > 1 or len(_node_edges(node, "next_nodes")) > 1


def _degree(node):
    """``"<n> prev, <n> next"`` summary of a node's edges."""
    return f"{len(_node_edges(node, 'prev_nodes'))} prev, {len(_node_edges(node, 'next_nodes'))} next"


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
        """Build the diagnostic lines logged when this guard trips.

        Reported, in order: the node the recursion looped on, the path from the
        nearest branching node down to it, the nodes revisited on the path, and the
        path itself (elided in the middle when very long).
        """
        labels = [self.describe(target) for target in self.path]
        lines = self._loop_lines(labels)
        lines += self._revisited_lines(labels)
        lines.append(f"{self.name} full path ({len(labels)} levels, {self.calls} calls):")
        lines += self._slice_lines(labels, 0, len(labels), PATH_LOG_LIMIT)
        return lines

    def _loop_lines(self, labels):
        """Name the looping node and the path from the nearest branching node to it."""
        if not labels:
            return ["no path recorded: the guard tripped outside any guarded call"]
        loop = self._find_loop(labels)
        if loop is None:
            # every node on the path is distinct: the recursion fans out (each level
            # re-expanding several predecessors) instead of coming back to a node
            deepest = len(labels) - 1
            lines = [
                f"no node was revisited on the path: {self.name} fans out rather than looping",
                f"deepest node: [{deepest}] {labels[deepest]}",
            ]
            return lines + self._branching_lines(labels, deepest, "deepest node")
        first, last, label = loop
        if last - first == 1:
            headline = (
                f"re-entry on node {label}: expanded again immediately, "
                "so every level of the chain doubles the work"
            )
        else:
            headline = f"loop on node {label}"
        lines = [
            headline,
            f"  revisited at depth {first} and depth {last} of {len(labels)}",
            f"  repeating segment ({last - first} level(s)):",
        ]
        lines += [f"  {line}" for line in self._slice_lines(labels, first, last + 1, LOOP_SEGMENT_LOG_LIMIT)]
        return lines + self._branching_lines(labels, first, "loop")

    def _branching_lines(self, labels, target_index, target_name):
        """Describe the path from the nearest branching node down to ``target_index``."""
        lines = []
        if _is_branching(self.path[target_index]):
            lines.append(f"the {target_name} itself is on a branching node ({_degree(self.path[target_index])})")
        # strictly above: a branching loop node is already reported, and the caller
        # needs the stretch of graph *leading to* it
        branch_index = self._nearest_branching(target_index - 1)
        if branch_index is None:
            lines.append(f"no branching node above the {target_name}: it hangs off the top-level entry")
            return lines + self._slice_lines(labels, 0, target_index + 1, PATH_LOG_LIMIT)
        lines.append(
            f"nearest branching above the {target_name}: "
            f"[{branch_index}] {labels[branch_index]} ({_degree(self.path[branch_index])})"
        )
        lines.append(f"  path from there to the {target_name}:")
        return lines + [
            f"  {line}" for line in self._slice_lines(labels, branch_index, target_index + 1, PATH_LOG_LIMIT)
        ]

    def _revisited_lines(self, labels):
        repeated = [(label, count) for label, count in Counter(labels).most_common(10) if count > 1]
        if not repeated:
            return []
        lines = ["nodes revisited on that path (likely dependency loop):"]
        return lines + [f"  {count}x {label}" for label, count in repeated]

    @staticmethod
    def _find_loop(labels):
        """Locate the innermost repetition on the path.

        A repetition spanning other nodes (``A -> B -> A``) is a graph loop and is
        preferred; an immediate repeat (``A -> A``) is the same node being expanded
        twice in a row, which is reported only when there is no loop to report.

        Args:
            labels: one diagnostic label per path level, outermost call first.

        Returns:
            ``(first_index, last_index, label)`` of the repetition whose second
            occurrence is the deepest — the one the guard actually tripped inside —
            or None when no node repeats.
        """
        last_seen = {}
        immediate = None
        spanning = None
        for index, label in enumerate(labels):
            previous = last_seen.get(label)
            if previous is not None:
                if index - previous > 1 and len(set(labels[previous:index])) > 1:
                    spanning = (previous, index, label)
                else:
                    immediate = (previous, index, label)
            last_seen[label] = index
        return spanning or immediate

    def _nearest_branching(self, from_index):
        """Index of the closest branching node at or above ``from_index``, or None."""
        for index in range(min(from_index, len(self.path) - 1), -1, -1):
            if _is_branching(self.path[index]):
                return index
        return None

    @staticmethod
    def _slice_lines(labels, start, end, limit):
        """Render ``labels[start:end]`` as indented ``[depth] label`` lines.

        Keeps ``limit`` entries at each end and elides the middle, so a very deep
        path stays readable in the log.
        """
        indexes = list(range(start, end))
        if len(indexes) > 2 * limit:
            head, tail = indexes[:limit], indexes[-limit:]
            omitted = len(indexes) - 2 * limit
            return (
                [f"  [{i}] {labels[i]}" for i in head]
                + [f"  ... {omitted} level(s) omitted ..."]
                + [f"  [{i}] {labels[i]}" for i in tail]
            )
        return [f"  [{i}] {labels[i]}" for i in indexes]


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
