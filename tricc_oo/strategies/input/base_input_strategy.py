import abc
import os

from tricc_oo.models.tricc import (
    TriccProject,
    TriccNodeMainStart,
    TriccSegment,
    node_container_for_root,
)
from tricc_oo.converters.utils import generate_id
from tricc_oo.visitors.tricc import (
    get_activity_wait,
    set_prev_next_node,
    export_proposed_diags,
    export_diags,
    create_determine_diagnosis_activity,
)
import logging

logger = logging.getLogger("default")


class BaseInputStrategy:
    input_path = None
    project = None
    processes = ["main"]

    def execute_linked_process(self, project):
        # create an overall activity only if not specified
        if "main" not in project.start_pages:
            page_processes = [
                (
                    p.root.process,
                    p,
                )
                for p in list(project.pages.values())
                if getattr(p.root, "process", None)
            ]
            sorted_pages = {}
            diags = []
            proposed_diags = []
            for a in project.pages.values():
                proposed_diags += export_proposed_diags(a, [])
                diags +=  export_diags(a, [])
            seen_diags = set()
            unique_diags = []
            for diag in proposed_diags:
                if diag.name not in seen_diags:
                    unique_diags.append(diag)
                    seen_diags.add(diag.name)
            # get the highest priority 
            for udiag in unique_diags:
                diag_map = [d.priority or 0 for d in diags if udiag.name == d.name[7:]]
                if diag_map:
                    udiag.priority = max((udiag.priority or 0), *diag_map)
            
            severity_order = {"severe": 3, "moderate": 2, "mild": 1, "light": 0}
            unique_diags = sorted(
                unique_diags,
                key=lambda x: (
                    -getattr(severity_order, x.severity or "light", 0),
                    x.label,
                ),
            )
            for process in self.processes:
                if process in [p[0] for p in page_processes]:
                    sorted_pages[process] = [p[1] for p in page_processes if p[0] == process]
                elif process == "determine-diagnosis" and diags:
                    diags_activity = create_determine_diagnosis_activity(unique_diags)
                    sorted_pages[process] = [diags_activity]
                    project.start_pages["determine-diagnosis"] = diags_activity
                    if isinstance(diags_activity, TriccSegment):
                        project.register_segment(diags_activity)
            root_process = sorted_pages[list(sorted_pages.keys())[0]][0].root
            root = TriccNodeMainStart(
                id=generate_id("s-main"),
                form_id=root_process.form_id,
                label=root_process.label,
                process="main",
            )
            nodes = {}
            nodes[root.id] = root
            app = node_container_for_root(
                root, id=generate_id("a-main"), name=root_process.name, nodes=nodes
            )
            root.activity = app
            root.group = app
            # loop back to app to avoid None
            app.activity = app
            app.group = app
            # setting the activity/group to main
            prev_bridge = root
            prev_process = None
            for process in self.processes:
                if process in sorted_pages:
                    nodes = {page.id: page for page in sorted_pages[process]}
                    if prev_process:
                        prev_bridge = get_activity_wait(
                            prev_bridge,
                            sorted_pages[prev_process],
                            nodes.values(),
                            activity=app,
                        )
                    else:
                        for a in nodes:
                            set_prev_next_node(prev_bridge, a, edge_only=True)
                    app.nodes[prev_bridge.id] = prev_bridge

                    for n in nodes.values():
                        n.activity = app
                        n.group = app
                        app.nodes[n.id] = n
                    prev_process = process

            return app
        else:
            return project.start_pages["main"]

    def __init__(self, input_path):
        self.input_path = input_path

    # walking function
    @abc.abstractmethod
    def execute(in_filepath, media_path):
        pass

    # ------------------------------------------------------------------
    # Building blocks, so several input strategies can feed one project
    # (tricc.yaml ``activity: {DrawioStrategy: [...], YamlStrategy: [...]}``).
    # ``execute`` == new_project + load + finalize for every strategy.
    # ------------------------------------------------------------------
    @staticmethod
    def new_project(project_config=None, intervention=None) -> TriccProject:
        project = TriccProject()
        if project_config is not None:
            project.title = project_config.title
            project.image_max_width = project_config.image_max_width()
            project.image_max_height = project_config.image_max_height()
            default_lang, languages = project_config.languages()
            if default_lang:
                project.lang_code = default_lang
                project.languages = languages
        project.intervention = intervention
        return project

    def load(self, file_content, media_path, project) -> None:
        """Read this strategy's files into ``project.pages``; no linking."""
        raise NotImplementedError

    @staticmethod
    def load_terminology(project, sources) -> None:
        """Load tricc.yaml ``terminology`` CodeSystems into ``project.code_systems``.

        ``sources`` is ``[(path, json text)]``. Keys follow the drawio import: the
        CodeSystem ``name`` (the concept-code prefix, e.g. ``demo`` for ``demo.fever``),
        falling back to its ``id``, so concepts added later by an input strategy land in
        the same CodeSystem.
        """
        import json

        from fhir.resources.codesystem import CodeSystem

        for path, text in sources:
            data = json.loads(text)
            if data.get("resourceType") != "CodeSystem":
                raise ValueError(f"{path}: terminology files must be FHIR CodeSystem resources")
            code_system = CodeSystem.model_validate(data)
            key = code_system.name or code_system.id
            if not key:
                raise ValueError(f"{path}: CodeSystem needs a name or id")
            if key in project.code_systems:
                raise ValueError(f"{path}: CodeSystem {key!r} is defined twice in terminology")
            if code_system.concept is None:
                code_system.concept = []
            project.code_systems[key] = code_system
            project.terminology_concepts.update((key, c.code) for c in code_system.concept)

    @staticmethod
    def load_libraries(project, sources) -> None:
        """Parse tricc.yaml ``libraries`` (``[(path, cql text)]``) into calculates."""
        from tricc_oo.converters.cql_library import build_library_calculates

        seen = {}
        for path, text in sources:
            for calc in build_library_calculates(text, path):
                if calc.name in seen:
                    raise ValueError(f"{path}: define {calc.name!r} is already defined in {seen[calc.name]}")
                seen[calc.name] = path
                project.library_calculates.append(calc)

    @staticmethod
    def write_terminology(project, media_path) -> None:
        """Write the project CodeSystems / ValueSets next to the media folder."""
        out_dir = os.path.dirname(media_path)
        for k, v in project.code_systems.items():
            with open(os.path.join(out_dir, f"{k}_codesystem.json"), "w", encoding="utf-8") as file:
                file.write(v.json(indent=4))
        for k, v in project.value_sets.items():
            with open(os.path.join(out_dir, f"{k}_valueset.json"), "w") as file:
                file.write(v.json(indent=4))

    @staticmethod
    def attach_library_calculates(project, page) -> None:
        """Hang the tricc.yaml library calculates on ``page`` as dangling calculates.

        The walkers schedule a page's prev-less calculates when they reach its root, so
        library defines join the stash next to the root and are processed once their
        references are ready -- exactly like a free-floating calculate drawn on the page.
        """
        calculates = getattr(project, "library_calculates", None) or []
        if page is None or not calculates:
            return
        for calc in calculates:
            if calc.id in page.nodes:
                continue
            calc.activity = page
            calc.group = page
            page.nodes[calc.id] = calc
            page.calculates.append(calc)

    def link_project(self, project):
        """Build the main flow from the loaded pages, then link and process them."""
        app = self.execute_linked_process(project)
        if app:
            project.start_pages["main"] = app
            project.pages[app.id] = app
            self.attach_library_calculates(project, app)
            self.process_pages(app, project)
            return project
        # Projects that only have non-main processes
        if project.start_pages:
            first = True
            for process, pages in project.start_pages.items():
                targets = pages if isinstance(pages, list) else [pages]
                for page in targets:
                    if first:
                        self.attach_library_calculates(project, page)
                        first = False
                    self.process_pages(page, project)
            return project
        return project if project.pages else None
