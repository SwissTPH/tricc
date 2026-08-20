"""
Base class for *test strategies*.

A test strategy is the third kind of strategy, alongside input and output. It
runs after an output strategy has finished and emits additional, non-deployable
material derived from that same build -- test specifications, coverage
manifests, fixtures.

The defining property is that the deployable artifact is produced by the output
strategy the user actually selected. A test strategy never substitutes for it
and never mutates it, so what gets tested is exactly what gets deployed.

Contract with the output strategy
---------------------------------

A test strategy may read, all optionally:

- ``output_strategy.df_survey`` -- the final XLSForm ``survey`` frame
- ``output_strategy.df_choice`` -- the final ``choices`` frame
- ``output_strategy.output_path`` -- where artifacts were written
- ``output_strategy.processes`` -- the processes the output covered

It must not write to any of them. Anything else on the output strategy is
private and may change without notice.

Node identity
-------------

By the time a test strategy runs, ``get_export_name()`` has already been called
for every exported node and cached on ``node.export_name``. Walking the graph
therefore yields the *same* names the deployed form uses -- which is the whole
reason this runs after export rather than as a separate pipeline.
"""

import abc
import logging
from typing import Any, Dict, List, Optional

logger = logging.getLogger("default")


class BaseTestStrategy(abc.ABC):
    """Emit test material for a completed build."""

    #: Processes this strategy covers, in order.
    processes = ["main"]

    def __init__(self, project, output_path, output_strategy=None):
        """
        Args:
            project: The processed ``TriccProject``.
            output_path: Directory the output strategy wrote to.
            output_strategy: The output strategy instance that just ran, or
                ``None`` when the test strategy is used standalone (degraded:
                XLSForm-specific detail will be unavailable).
        """
        self.project = project
        self.output_path = output_path
        self.output_strategy = output_strategy

    # -- lifecycle ---------------------------------------------------------

    @abc.abstractmethod
    def execute(self):
        """Produce the test material. Called once, after the output strategy."""

    # -- output strategy accessors (the documented coupling) ---------------

    @property
    def survey_frame(self):
        """The generated ``survey`` frame, or ``None`` if the output has none."""
        return getattr(self.output_strategy, "df_survey", None)

    @property
    def choice_frame(self):
        """The generated ``choices`` frame, or ``None``."""
        return getattr(self.output_strategy, "df_choice", None)

    @property
    def output_strategy_name(self) -> Optional[str]:
        """Class name of the output strategy that produced the artifacts."""
        return type(self.output_strategy).__name__ if self.output_strategy else None

    def survey_rows_by_name(self) -> Dict[str, dict]:
        """Index the ``survey`` frame by its ``name`` column.

        Returns:
            ``{name: row}``; empty when no frame is available. The first row
            wins, matching how a form runtime resolves a duplicated name.
        """
        rows: Dict[str, dict] = {}
        frame = self.survey_frame
        if frame is None or not len(frame):
            return rows
        for record in frame.fillna("").to_dict(orient="records"):
            name = str(record.get("name", "")).strip()
            if name and name not in rows:
                rows[name] = record
        return rows

    def choices_by_list(self) -> Dict[str, List[dict]]:
        """Index the ``choices`` frame by ``list_name``."""
        lists: Dict[str, List[dict]] = {}
        frame = self.choice_frame
        if frame is None or not len(frame):
            return lists
        for record in frame.fillna("").to_dict(orient="records"):
            list_name = str(record.get("list_name", "")).strip()
            value = str(record.get("value", "")).strip()
            if not list_name or not value:
                continue
            lists.setdefault(list_name, []).append(
                {"value": value, "label": str(record.get("label", "")).strip() or None}
            )
        return lists

    # -- graph traversal ---------------------------------------------------

    def all_nodes(self) -> List[Any]:
        """Every node object reachable by any means, deduplicated.

        Graph traversal alone is not sufficient. By the time an output strategy
        has finished exporting, ``next_nodes`` is largely empty -- on a real
        518-question form a walk from the process roots reaches barely a dozen
        nodes. The activities' own ``nodes`` and ``calculates`` collections are
        the reliable source; the walk is kept because it also picks up spliced-in
        activity *instances* that the base activities do not hold.

        Returns:
            Node objects, deduplicated by identity, walk order first.
        """
        collected: List[Any] = []
        seen = set()

        def take(node) -> None:
            if node is None or id(node) in seen:
                return
            seen.add(id(node))
            collected.append(node)

        for node in self.walk_nodes():
            take(node)

        activities: List[Any] = []
        for source in (getattr(self.project, "start_pages", {}) or {},
                       getattr(self.project, "pages", {}) or {}):
            for page in source.values():
                activities.extend(page if isinstance(page, (list, tuple)) else [page])

        for activity in activities:
            if activity is None:
                continue
            take(getattr(activity, "root", None))
            for node in (getattr(activity, "nodes", {}) or {}).values():
                take(node)
            for node in getattr(activity, "calculates", []) or []:
                take(node)

        return collected

    def walk_nodes(self) -> List[Any]:
        """Collect every node reachable from the start pages, in traversal order.

        Follows ``next_nodes`` from each process root, and descends into any
        activity encountered (its ``root`` and its ``calculates``), because the
        exporter does the same: a goto or link_out splices an activity *instance*
        into the graph, and its calculates never appear in the ``next_nodes``
        chain.

        Only instances reachable from the roots are returned. Sweeping
        ``project.pages`` instead would pick up the *base* activities, whose
        nodes were never exported, and every one of them would then show up as a
        phantom "missing from survey".

        Returns:
            The reachable nodes, deduplicated, in breadth-first order.
        """
        collected: List[Any] = []
        seen = set()
        queued = set()
        queue: List[Any] = []

        def enqueue(candidate) -> None:
            if candidate is None or id(candidate) in seen or id(candidate) in queued:
                return
            queued.add(id(candidate))
            queue.append(candidate)

        start_pages = getattr(self.project, "start_pages", {}) or {}
        ordered_pages = [start_pages.get(process) for process in self.processes]
        ordered_pages += [page for page in start_pages.values() if page not in ordered_pages]

        for page in ordered_pages:
            # A process may map to a list of activities rather than one.
            for activity in page if isinstance(page, (list, tuple)) else [page]:
                if activity is None:
                    continue
                enqueue(getattr(activity, "root", None))
                for extra in list(getattr(activity, "calculates", []) or []):
                    enqueue(extra)

        while queue:
            node = queue.pop(0)
            queued.discard(id(node))
            if node is None or id(node) in seen:
                continue
            seen.add(id(node))
            collected.append(node)

            for successor in getattr(node, "next_nodes", None) or []:
                enqueue(successor)

            # Descend into a nested activity instance the same way export does.
            activity = getattr(node, "activity", None)
            if activity is not None and activity is not node:
                enqueue(getattr(activity, "root", None))
                for extra in list(getattr(activity, "calculates", []) or []):
                    enqueue(extra)

        return collected

    def form_id(self) -> Optional[str]:
        """The form id declared on the main start node, if any."""
        start_pages = getattr(self.project, "start_pages", {}) or {}
        page = start_pages.get(self.processes[0])
        # A process may map to a list of activities rather than a single one.
        for activity in page if isinstance(page, (list, tuple)) else [page]:
            form_id = getattr(getattr(activity, "root", None), "form_id", None)
            if form_id:
                return str(form_id)
        return None
