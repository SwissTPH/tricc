"""
OpenSRPStrategy: openSRP / fhircore-specific FHIR export strategy for TRICC.

Extends ``FHIRStrategy`` with:
- One **Intervention PlanDefinition** for the whole project (today: one project = one
  Intervention) — one nested ``action`` per non-empty process, ``definitionCanonical``
  → **Questionnaire** for Start care (**due now**). Each action's ``trigger`` carries
  *both* the process-name named-event *and* the ``available-care`` named-event, so
  fhircore's ``NamedEventInterventionService`` discovers this single PlanDefinition
  directly (no wrapping catalog PD — see ``feature/careplan-intervention-plandefinition.md``).
- Optional Task StructureMaps for the **upcoming planning** feature only
  (Questionnaire **not due now** → Task with ``reasonReference`` → form later)
- RelatedPerson client-register contract (patient always = child; PI identifier)
- Top-level Composition (JSON only — no FSH dual-write)

**Do not** use Task / ActivityDefinition as the Start-care launch target. Task wrapping
is reserved for planning when the questionnaire is not due now. See
``feature/opensrp-register.md`` §2.1 and ``feature/opensrp-export-hygiene.md`` §4.

Output folder structure (matches fhircore expected layout)::

    output/<form_id>/
    ├── Composition.json
    ├── plan-definition/   # single Intervention PD
    ├── structure-map/     # extraction maps (QR → Observation/Condition) + optional Task maps
    ├── binary/
    ├── contract/          # related-person-contract.json
    └── …                  # Questionnaire / Library JSON from FHIRStrategy

Usage::

    tricc -i input.drawio -o output/ -O OpenSRPStrategy
"""

from __future__ import annotations

import json
import logging
import os
import shutil
import stat
from pathlib import Path
from typing import Dict, List, Optional

from tricc_oo.converters.fhir.ids import (
    fhir_resource_id,
    readable_resource_filename,
    to_fhir_id,
)
from tricc_oo.converters.fhir.related_person import (
    AVAILABLE_CARE_NAMED_EVENT,
    RELATED_PERSON_CONTRACT,
    structure_map_related_person_hints,
)
from tricc_oo.converters.fhir.questionnaire_item_mapper import (
    build_choice_orientation_extension,
)
from tricc_oo.converters.fhir.structuremap import target_structuremap_extension
from tricc_oo.strategies.output.fhir_form import (
    DEFAULT_BASE_URL,
    FHIRStrategy,
)
from tricc_oo.strategies.registry import register_output_strategy
from tricc_oo.visitors.utils import PROCESS_ORDER, PROCESSES

logger = logging.getLogger("default")

# ---------------------------------------------------------------------------
# openSRP / fhircore profile URLs
# ---------------------------------------------------------------------------
OPENSRP_QUESTIONNAIRE_PROFILE = (
    "http://hl7.org/fhir/uv/sdc/StructureDefinition/sdc-questionnaire"
)
OPENSRP_PLANDEFINITION_PROFILE = (
    "http://hl7.org/fhir/StructureDefinition/PlanDefinition"
)
OPENSRP_COMPOSITION_PROFILE = (
    "http://hl7.org/fhir/StructureDefinition/Composition"
)

# cpg-common-process trigger system
CPG_COMMON_PROCESS_SYSTEM = "http://hl7.org/fhir/uv/cpg/CodeSystem/cpg-common-process"

# Extension URLs used by fhircore
FHIRCORE_EXT_CQL_INPUT = (
    "http://hl7.org/fhir/uv/sdc/StructureDefinition/sdc-questionnaire-cqlInputResources"
)
FHIRCORE_EXT_PLAN_DEFINITIONS = (
    "http://hl7.org/fhir/uv/sdc/StructureDefinition/sdc-questionnaire-planDefinitions"
)

# App package tag — Android/cdss shell sync pulls content with:
#   ResourceType?_tag=https://smartregister.org/app-id|{app_id}
# Override via OPENSRP_APP_ID or FHIR_APP_ID (default ``cdss``).
APP_ID_TAG_SYSTEM = "https://smartregister.org/app-id"
DEFAULT_OPENSRP_APP_ID = "cdss"


@register_output_strategy("OpenSRPStrategy")
class OpenSRPStrategy(FHIRStrategy):
    """openSRP / fhircore output strategy.

    Inherits all standard FHIR SDC generation from ``FHIRStrategy`` and adds
    openSRP-specific resources: PlanDefinition (Questionnaire launch for Start
    care), optional Task StructureMaps for **planning / not-due-now**, and
    Composition.

    Artifact mode is **JSON only** (no FSH dual-write).

    Start care uses ``definitionCanonical`` → Questionnaire. Task-wrapped
    Questionnaires are only for the upcoming planning feature when the form is
    not due now.

    Attributes:
        plan_definitions: Dict with a single ``"intervention"`` key → the Intervention
            PlanDefinition resource dict (one action per process, each action also
            carrying the ``available-care`` named-event trigger for Start-care discovery).
        composition: The top-level Composition resource dict (built at export time).
        process_chain: Ordered non-empty process names (graph discovery order).
    """

    processes = ["main"]

    def __init__(self, project, output_path: str, base_url: str = DEFAULT_BASE_URL):
        """Initialise the OpenSRPStrategy.

        Args:
            project: The TRICC project object.
            output_path: Directory path for output files.
            base_url: Canonical base URL for FHIR resources.
        """
        super().__init__(project, output_path, base_url)
        self.plan_definitions: Dict[str, dict] = {}
        self.composition: Optional[dict] = None
        self.process_chain: List[str] = []
        # App id for meta.tag (content delivery) — not the package Composition identifier.
        self.app_id: str = (
            os.environ.get("OPENSRP_APP_ID")
            or os.environ.get("FHIR_APP_ID")
            or DEFAULT_OPENSRP_APP_ID
        ).strip() or DEFAULT_OPENSRP_APP_ID

    def _boolean_choice_orientation_extension(self) -> Optional[dict]:
        """Yes/No sit side by side in the openSRP questionnaire UI."""
        return build_choice_orientation_extension("horizontal")

    # ── Lifecycle override ────────────────────────────────────────────────────

    def execute(self):
        """Run the full openSRP export pipeline.

        Calls the parent FHIR pipeline then adds openSRP-specific resources.
        """
        super().execute()

    def export(self, start_pages, version: str = ""):
        """Write all generated resources to the output directory.

        Extends the parent export with PlanDefinition, Task StructureMaps,
        and Composition (JSON only).

        Args:
            start_pages: Dict of start pages from the project.
            version: Build version string.
        """
        form_id = self.resolve_form_id(start_pages)
        base = Path(self.output_path) / form_id

        # Drop empty questionnaires before PD / Task / catalog generation
        self._prune_empty_questionnaires()
        # Graph discovery order: questionnaires keys are insertion-ordered during walk
        self.process_chain = list(self.questionnaires.keys())

        # Build openSRP-specific resources before writing.
        # One Intervention PlanDefinition for the whole project (1 process = 1 action =
        # 1 Questionnaire), shared by every process — see
        # feature/careplan-intervention-plandefinition.md.
        if self.process_chain:
            intervention_pd = self.generate_intervention_plandefinition(version)
            self.plan_definitions["intervention"] = intervention_pd
            for process in self.process_chain:
                sm = self.generate_task_structuremap(process, version)
                if sm is not None:
                    # Key by process for stable lookup; id inside JSON remains UUID
                    self.structuremaps[process] = sm
                # Wire planDefinitions + cqlInputResources onto the Questionnaire
                self._wire_questionnaire_extensions(process, intervention_pd, version)

        self.composition = self.generate_composition(version)

        # Tag all clinical resources for shell app-id sync before any write
        self._stamp_package_app_id_tags()

        # Remove stale UUID-named files from prior exports (filename ≠ REST id)
        self._clean_stale_package_files(base)

        # Write standard FHIR resources (questionnaire, library, FML stubs, …)
        super().export(start_pages, version)

        # Write openSRP-specific resources (JSON only — no FSH)
        self._write_plan_definitions(base, version)
        self._write_structure_maps(base)
        self._write_composition(base)
        self._write_image_binaries(base)
        self._write_related_person_contract(base)
        self._copy_push_scripts(base)

        logger.info(
            "OpenSRPStrategy: exported openSRP package to %s (app_id tag=%s)",
            base,
            self.app_id,
        )

    def validate(self):
        """Validate the generated openSRP resources (calls parent FHIR validation first).

        Emits warnings (never raises) for detected issues.
        """
        super().validate()
        for process, q in (self.questionnaires or {}).items():
            if self.is_questionnaire_empty(q):
                logger.warning(
                    "OpenSRPStrategy: empty Questionnaire still present for process '%s'",
                    process,
                )
        # Intervention PD: one wrapper action carrying available-care once, nested with
        # one child action per process — each child must launch its Questionnaire and
        # carry its own process trigger + the tricc-process/tricc-process-order extensions.
        intervention_pd = self.plan_definitions.get("intervention")
        if intervention_pd is not None:
            top_actions = intervention_pd.get("action") or []
            if not top_actions:
                logger.warning("Intervention PlanDefinition has no actions")
            wrapper = top_actions[0] if top_actions else {}
            wrapper_trigger_names = [
                t.get("name")
                for t in wrapper.get("trigger", [])
                if t.get("type") == "named-event"
            ]
            if AVAILABLE_CARE_NAMED_EVENT not in wrapper_trigger_names:
                logger.warning(
                    "Intervention PlanDefinition wrapper action missing named-event "
                    f"'{AVAILABLE_CARE_NAMED_EVENT}'"
                )
            child_actions = wrapper.get("action") or []
            if not child_actions:
                logger.warning("Intervention PlanDefinition wrapper action has no child actions")
            for action in child_actions:
                process = action.get("id") or "?"
                def_can = action.get("definitionCanonical") or ""
                # Start care / openSRP: launch Questionnaire directly
                if "Questionnaire/" not in def_can:
                    logger.warning(
                        "Intervention PlanDefinition action '%s' definitionCanonical "
                        "should reference a Questionnaire (got %r)",
                        process,
                        def_can,
                    )
                if def_can.startswith("#") or "ActivityDefinition" in def_can:
                    logger.warning(
                        "Intervention PlanDefinition action '%s' still uses Task "
                        "ActivityDefinition; prefer Questionnaire canonical",
                        process,
                    )
                trigger_names = [
                    t.get("name")
                    for t in action.get("trigger", [])
                    if t.get("type") == "named-event"
                ]
                if not trigger_names:
                    logger.warning(
                        "Intervention PlanDefinition action '%s' missing its process "
                        "named-event trigger",
                        process,
                    )
                extension_urls = [e.get("url") for e in action.get("extension", [])]
                if not extension_urls or not any(
                    url and url.endswith("tricc-process-order") for url in extension_urls
                ):
                    logger.warning(
                        "Intervention PlanDefinition action '%s' missing "
                        "tricc-process-order extension",
                        process,
                    )

        if self.composition is None:
            logger.warning("Composition resource was not generated")
        logger.info("OpenSRPStrategy: openSRP validation complete")

    # ── openSRP resource generators ───────────────────────────────────────────

    @staticmethod
    def is_questionnaire_empty(q: Optional[dict]) -> bool:
        """Return True when the questionnaire has no items (``item: []`` or missing).

        Args:
            q: Questionnaire resource dict, or None.

        Returns:
            True if empty / missing; False if at least one top-level item exists.
        """
        if not isinstance(q, dict):
            return True
        items = q.get("item")
        return not items

    def _prune_empty_questionnaires(self) -> None:
        """Remove questionnaires with ``item: []`` and drop orphan per-process assets."""
        empty_processes = [
            process
            for process, q in list(self.questionnaires.items())
            if self.is_questionnaire_empty(q)
        ]
        for process in empty_processes:
            logger.warning(
                "OpenSRPStrategy: dropping empty Questionnaire for process '%s' (item: [])",
                process,
            )
            del self.questionnaires[process]
            # Drop process-scoped CQL / libraries if present (keys may be segment names)
            self.cql_defines.pop(process, None)
            self.cql_libraries.pop(process, None)
            self.libraries.pop(process, None)
            self.extraction_maps.pop(process, None)
            self.extraction_rules.pop(process, None)
            self.fml_mappings.pop(process, None)
            # StructureMaps keyed by process id if any
            for sm_id in list(self.structuremaps.keys()):
                if process in sm_id:
                    del self.structuremaps[sm_id]

    def _next_process(self, process: str) -> Optional[str]:
        """Return the next non-empty process in graph discovery order, if any.

        Args:
            process: Current process name.

        Returns:
            Next process name or None when this is the last in the chain.
        """
        chain = self.process_chain or list(self.questionnaires.keys())
        try:
            idx = chain.index(process)
        except ValueError:
            return None
        if idx + 1 < len(chain):
            return chain[idx + 1]
        return None

    def _questionnaire_ref(self, process: str) -> tuple[str, str]:
        """Return (questionnaire_id, questionnaire_canonical_url) for a process.

        Args:
            process: Process name key in ``self.questionnaires``.

        Returns:
            Tuple of id and absolute Questionnaire URL.
        """
        q = (self.questionnaires or {}).get(process) or {}
        form_key = getattr(self, "_form_id", None) or self.fhir_form_id
        q_id = q.get("id") or fhir_resource_id(form_key, "Questionnaire", process)
        q_url = q.get("url") or f"{self.base_url}/Questionnaire/{q_id}"
        # Prefer base_url canonical when export used a placeholder example.com URL
        if "example.com" in q_url or not q_url.startswith("http"):
            q_url = f"{self.base_url}/Questionnaire/{q_id}"
        return q_id, q_url

    def _process_resource_ids(self, process: str) -> dict:
        """Return UUID FHIR ids for a process's openSRP resources (stable uuid5).

        Args:
            process: Process name from the graph.

        Returns:
            Dict with keys pd_id, ad_id, sm_id, lib_id, logical names (all REST ids are UUIDs).
        """
        form_key = getattr(self, "_form_id", None) or self.fhir_form_id
        proc = to_fhir_id(process)
        return {
            "pd_id": fhir_resource_id(form_key, "PlanDefinition", process),
            "ad_id": fhir_resource_id(form_key, "ActivityDefinition", process, "task"),
            "sm_id": fhir_resource_id(form_key, "StructureMap", process, "task"),
            "lib_id": fhir_resource_id(form_key, "Library", process),
            "pd_name": to_fhir_id(self.fhir_form_id, proc, "PD"),
            "ad_name": to_fhir_id(self.fhir_form_id, proc, "task-activity"),
            "sm_name": to_fhir_id(self.fhir_form_id, proc, "task"),
            "lib_name": to_fhir_id(self.fhir_form_id, proc),
        }

    def _intervention_resource_ids(self) -> dict:
        """Return stable ids/names for the single project-wide Intervention PlanDefinition.

        Returns:
            Dict with keys ``pd_id`` (UUID) and ``pd_name`` (human-readable).
        """
        form_key = getattr(self, "_form_id", None) or self.fhir_form_id
        return {
            "pd_id": fhir_resource_id(form_key, "PlanDefinition", "intervention"),
            "pd_name": to_fhir_id(self.fhir_form_id, "intervention", "PD"),
        }

    def _process_order(self, process: str, assigned: Dict[str, int]) -> int:
        """Return the canonical order value for *process* (10, 20, 30… by PROCESSES rank).

        Process names not in the canonical ``PROCESSES`` list get the next free slot
        after the highest known order, assigned in discovery order and cached in
        *assigned* so repeated calls for the same export are stable.

        Args:
            process: Process name.
            assigned: Mutable cache of already-assigned custom orders for this export.

        Returns:
            Integer order value.
        """
        order = PROCESS_ORDER.get(process)
        if order is not None:
            return order
        if process not in assigned:
            base = max(PROCESS_ORDER.values())
            taken = set(PROCESS_ORDER.values()) | set(assigned.values())
            next_order = base + 10
            while next_order in taken:
                next_order += 10
            assigned[process] = next_order
        return assigned[process]

    def generate_intervention_plandefinition(self, version: str) -> dict:
        """Build the single Intervention PlanDefinition for this project.

        Today one project is one Intervention (see
        ``feature/careplan-intervention-plandefinition.md``): one wrapper action
        carrying the ``available-care`` named-event **once** (not repeated on every
        child — see ``feature/20260812-intervention-order-and-dedup.md``), nested with
        one child ``action`` per non-empty process, in graph discovery order, each
        ``definitionCanonical`` → that process's Questionnaire
        (**1 process = 1 action = 1 Questionnaire**).

        Each child action keeps its own process-name named-event trigger (for possible
        direct per-process invocation) and carries two new extensions: ``tricc-process``
        (the process name) and ``tricc-process-order`` (the canonical cpg-common-process
        order, 10/20/30…) — the latter lets the openSRP client compare "which unlocked
        action is earliest" across several selected Interventions/PlanDefinitions.

        This is deliberately same-resource nesting (``action.action``), not a second
        linked PlanDefinition: fhircore's ``NamedEventInterventionService`` still
        evaluates each same-resource child action's own applicability individually,
        unlike the old wrapping catalog PD (removed 2026-08-12) whose cross-resource
        ``definitionCanonical`` link caused every child to be resolved unconditionally.

        No applicability/eligibility ``condition`` is emitted yet.

        Args:
            version: Build version string.

        Returns:
            PlanDefinition resource dict.
        """
        ids = self._intervention_resource_ids()
        pd_id = ids["pd_id"]
        form_label = getattr(self, "_form_id", None) or self.fhir_form_id

        child_actions: List[dict] = []
        lib_urls: List[str] = []
        custom_orders: Dict[str, int] = {}
        for process in self.process_chain:
            proc_ids = self._process_resource_ids(process)
            lib_id = proc_ids["lib_id"]
            libs = getattr(self, "libraries", None) or {}
            lib = libs.get(process) or libs.get(to_fhir_id(process))
            if isinstance(lib, dict) and lib.get("id"):
                lib_id = lib["id"]
            lib_url = f"{self.base_url}/Library/{lib_id}"
            if lib_url not in lib_urls:
                lib_urls.append(lib_url)

            q_id, q_url = self._questionnaire_ref(process)
            # Determine trigger code (use process name if it's a known cpg-common-process)
            trigger_code = process if process in PROCESSES else process or "registration"
            process_title = process.replace("-", " ").replace("_", " ").title()
            q = self.questionnaires.get(process) if getattr(self, "questionnaires", None) else None
            q_title = q.get("title") or q.get("name") if isinstance(q, dict) else None
            action_title = q_title or f"Launch {process_title}"

            child_actions.append({
                "id": fhir_resource_id(form_label, "action", process),
                "title": action_title,
                "description": f"Intervention / process: {process}",
                "trigger": [
                    {
                        "type": "named-event",
                        "name": trigger_code,
                    },
                ],
                "extension": [
                    {
                        "url": f"{self.base_url}/StructureDefinition/tricc-process",
                        "valueString": process,
                    },
                    {
                        "url": f"{self.base_url}/StructureDefinition/tricc-process-order",
                        "valueInteger": self._process_order(process, custom_orders),
                    },
                ],
                # openSRP APPLY_NAMED_EVENT → launch Questionnaire by canonical id
                "definitionCanonical": q_url,
            })

        # Wrapper action: carries the available-care named-event once, at "PD level" —
        # fhircore discovers this PlanDefinition via this single trigger, then evaluates
        # each nested child action's own applicability individually.
        wrapper_action = {
            "id": "available-care",
            "title": f"{form_label} – Available care",
            "trigger": [
                {
                    "type": "named-event",
                    "name": AVAILABLE_CARE_NAMED_EVENT,
                },
            ],
            "action": child_actions,
        }

        return {
            "resourceType": "PlanDefinition",
            "id": pd_id,
            "meta": {"profile": [OPENSRP_PLANDEFINITION_PROFILE]},
            "url": f"{self.base_url}/PlanDefinition/{pd_id}",
            "name": ids["pd_name"],
            "title": f"{form_label} – Intervention",
            "version": version or "1.0.0",
            # active: Android named-event discovery loads local PDs after tag-sync
            "status": "active",
            "experimental": False,
            "type": {
                "coding": [
                    {
                        "system": "http://terminology.hl7.org/CodeSystem/plan-definition-type",
                        "code": "clinical-protocol",
                    }
                ]
            },
            "library": lib_urls,
            "action": [wrapper_action],
        }

    def generate_task_structuremap(self, process: str, version: str) -> Optional[dict]:
        """Build a StructureMap that creates Tasks wrapping Questionnaires.

        **Planning / not-due-now only (upcoming feature).** Start care does **not**
        use these maps: openSRP launches Questionnaire via PD
        ``definitionCanonical`` when the form is due now.

        When planning is implemented, Task + ``reasonReference`` → Questionnaire
        is used to schedule work that is **not due now** (task register / worklist).
        Optional multi-process chaining (``extractNextTaskOnDone``) may still apply
        after a form is completed.

        * **This process Task**: ``reasonReference`` → this process Questionnaire.
        * **Next process Task** (when this questionnaire is done): if a successor
          process exists in graph order, emit a second Task with
          ``reasonReference`` → next Questionnaire.

        Args:
            process: Current process name.
            version: Build version string.

        Returns:
            StructureMap resource dict, or None if no questionnaire for process.
        """
        if process not in (self.questionnaires or {}):
            return None

        ids = self._process_resource_ids(process)
        sm_id = ids["sm_id"]
        # Reference the shared Intervention PD (not a per-process leaf PD — see
        # feature/careplan-intervention-plandefinition.md); fall back to the uuid5
        # leaf id only if the Intervention PD hasn't been built yet (unit tests).
        intervention_pd = next(iter(self.plan_definitions.values()), None)
        pd_id = intervention_pd["id"] if intervention_pd else ids["pd_id"]
        q_id, q_url = self._questionnaire_ref(process)
        process_title = process.replace("-", " ").replace("_", " ").title()

        next_process = self._next_process(process)
        next_q_id = next_q_url = None
        if next_process:
            next_q_id, next_q_url = self._questionnaire_ref(next_process)

        # FML for planning (not due now). Not wired as Start-care definitionCanonical.
        fml_lines = [
            f"map \"{self.base_url}/StructureMap/{sm_id}\" = '{sm_id}'",
            "",
            'uses "http://hl7.org/fhir/StructureDefinition/Parameters" as source',
            'uses "http://hl7.org/fhir/StructureDefinition/Task" as target',
            "",
            f"// Planning only (not due now): Task.reasonReference → Questionnaire/{q_id}",
            "group extractThisTask(source src : Parameters, target task : Task) {",
            "  src -> task.status = 'ready',",
            "         task.intent = 'plan',",
            f"         task.description = 'Complete {process_title}',",
            f"         task.reasonReference = create('Reference') as ref,",
            f"           ref.reference = 'Questionnaire/{q_id}',",
            f"           ref.display = '{q_url}' \"r_this_task\";",
            "}",
        ]
        if next_process and next_q_id:
            next_title = next_process.replace("-", " ").replace("_", " ").title()
            fml_lines += [
                "",
                f"// On questionnaire done → next process '{next_process}' Task",
                "group extractNextTaskOnDone(source src : Parameters, target task : Task) {",
                "  src -> task.status = 'ready',",
                "         task.intent = 'plan',",
                f"         task.description = 'Complete {next_title} (after {process})',",
                f"         task.reasonReference = create('Reference') as ref,",
                f"           ref.reference = 'Questionnaire/{next_q_id}',",
                f"           ref.display = '{next_q_url}' \"r_next_task\";",
                "}",
            ]

        fml_text = "\n".join(fml_lines) + "\n"

        structuremap: dict = {
            "resourceType": "StructureMap",
            "id": sm_id,
            "url": f"{self.base_url}/StructureMap/{sm_id}",
            "name": ids["sm_name"].replace("-", "_"),
            "title": f"Task map for {process}",
            "version": version or "1.0.0",
            "status": "draft",
            "description": (
                f"Planning / not-due-now: Task.reasonReference → Questionnaire/{q_id}. "
                "Not used for Start care (due now launches Questionnaire directly). "
                + (
                    f"When done, may create Task for next process '{next_process}' "
                    f"(Questionnaire/{next_q_id})."
                    if next_process
                    else "No successor process in graph order."
                )
            ),
            "structure": [
                {
                    "url": "http://hl7.org/fhir/StructureDefinition/Parameters",
                    "mode": "source",
                },
                {
                    "url": "http://hl7.org/fhir/StructureDefinition/Task",
                    "mode": "target",
                },
            ],
            # Machine-readable chain metadata for tooling / tests
            "extension": [
                {
                    "url": f"{self.base_url}/StructureDefinition/tricc-task-questionnaire",
                    "valueReference": {"reference": f"Questionnaire/{q_id}"},
                },
                {
                    "url": f"{self.base_url}/StructureDefinition/tricc-task-plandefinition",
                    "valueReference": {"reference": f"PlanDefinition/{pd_id}"},
                },
            ],
            "group": [
                {
                    "name": "extractThisTask",
                    "typeMode": "none",
                    "input": [
                        {"name": "src", "type": "Parameters", "mode": "source"},
                        {"name": "task", "type": "Task", "mode": "target"},
                    ],
                    "rule": [
                        {
                            "name": "setReasonReference",
                            "source": [{"context": "src"}],
                            "target": [
                                {
                                    "context": "task",
                                    "contextType": "variable",
                                    "element": "reasonReference",
                                    "transform": "copy",
                                    "parameter": [
                                        {
                                            "valueId": f"Questionnaire/{q_id}",
                                        }
                                    ],
                                }
                            ],
                        }
                    ],
                }
            ],
            "text": {
                "status": "generated",
                "div": (
                    f'<div xmlns="http://www.w3.org/1999/xhtml">'
                    f"<pre>{_xml_escape(fml_text)}</pre></div>"
                ),
            },
        }

        if next_process and next_q_id:
            structuremap["extension"].append(
                {
                    "url": f"{self.base_url}/StructureDefinition/tricc-next-task-questionnaire",
                    "valueReference": {"reference": f"Questionnaire/{next_q_id}"},
                }
            )
            structuremap["extension"].append(
                {
                    "url": f"{self.base_url}/StructureDefinition/tricc-next-process",
                    "valueString": next_process,
                }
            )
            structuremap["group"].append(
                {
                    "name": "extractNextTaskOnDone",
                    "typeMode": "none",
                    "documentation": (
                        f"Run when Questionnaire/{q_id} is completed; "
                        f"creates Task for Questionnaire/{next_q_id}."
                    ),
                    "input": [
                        {"name": "src", "type": "Parameters", "mode": "source"},
                        {"name": "task", "type": "Task", "mode": "target"},
                    ],
                    "rule": [
                        {
                            "name": "setNextReasonReference",
                            "source": [{"context": "src"}],
                            "target": [
                                {
                                    "context": "task",
                                    "contextType": "variable",
                                    "element": "reasonReference",
                                    "transform": "copy",
                                    "parameter": [
                                        {
                                            "valueId": f"Questionnaire/{next_q_id}",
                                        }
                                    ],
                                }
                            ],
                        }
                    ],
                }
            )

        # Keep FML text available for writers / debug (non-FHIR key stripped on write if needed)
        structuremap["_fml"] = fml_text
        return structuremap

    def generate_composition(self, version: str) -> dict:
        """Build the top-level Composition resource (fhircore config manifest).

        The Composition references all generated resources as required by the
        fhircore configuration model.

        Args:
            version: Build version string.

        Returns:
            Composition resource dict.
        """
        form_label = getattr(self, "_form_id", None) or self.fhir_form_id
        form_key = getattr(self, "_form_id", None) or self.fhir_form_id
        comp_id = fhir_resource_id(form_key, "Composition", "package")
        sections = []

        # Questionnaires section
        q_entries = [
            {"reference": f"Questionnaire/{q['id']}"}
            for q in (self.questionnaires or {}).values()
        ]
        if q_entries:
            sections.append({
                "title": "Questionnaires",
                "code": {
                    "coding": [{"system": "http://hl7.org/fhir/resource-types", "code": "Questionnaire"}]
                },
                "entry": q_entries,
            })

        # PlanDefinitions section (single Intervention PD)
        pd_entries = [
            {"reference": f"PlanDefinition/{pd['id']}"}
            for pd in self.plan_definitions.values()
        ]
        if pd_entries:
            sections.append({
                "title": "PlanDefinitions",
                "code": {
                    "coding": [{"system": "http://hl7.org/fhir/resource-types", "code": "PlanDefinition"}]
                },
                "entry": pd_entries,
            })

        # Libraries section (use actual Library resource ids / UUIDs)
        lib_entries = []
        for lib in (self.libraries or {}).values():
            if isinstance(lib, dict) and lib.get("id"):
                lib_entries.append({"reference": f"Library/{lib['id']}"})
        if not lib_entries:
            # Fallback when libraries not yet assembled (unit tests)
            helper_id = fhir_resource_id(form_key, "Library", "Helper")
            lib_entries = [{"reference": f"Library/{helper_id}"}] + [
                {
                    "reference": f"Library/{fhir_resource_id(form_key, 'Library', process)}"
                }
                for process in (self.questionnaires or {})
            ]
        if lib_entries:
            sections.append({
                "title": "Libraries",
                "code": {
                    "coding": [{"system": "http://hl7.org/fhir/resource-types", "code": "Library"}]
                },
                "entry": lib_entries,
            })

        # StructureMaps section (extraction first, then optional Task/planning maps)
        sm_entries = [
            {"reference": f"StructureMap/{sm['id']}"}
            for sm in list((self.extraction_maps or {}).values())
            + list((self.structuremaps or {}).values())
            if isinstance(sm, dict) and sm.get("id")
        ]
        if sm_entries:
            sections.append({
                "title": "StructureMaps",
                "code": {
                    "coding": [{"system": "http://hl7.org/fhir/resource-types", "code": "StructureMap"}]
                },
                "entry": sm_entries,
            })

        # ValueSets section
        vs_entries = [
            {"reference": f"ValueSet/{vs_id}"}
            for vs_id in self.valuesets
        ]
        if vs_entries:
            sections.append({
                "title": "ValueSets",
                "code": {
                    "coding": [{"system": "http://hl7.org/fhir/resource-types", "code": "ValueSet"}]
                },
                "entry": vs_entries,
            })

        # Binaries section (images)
        bin_entries = [
            {"reference": f"Binary/{b['id']}"}
            for b in self.binaries
        ]
        if bin_entries:
            sections.append({
                "title": "Binaries",
                "code": {
                    "coding": [{"system": "http://hl7.org/fhir/resource-types", "code": "Binary"}]
                },
                "entry": bin_entries,
            })

        return {
            "resourceType": "Composition",
            "id": comp_id,
            "meta": {"profile": [OPENSRP_COMPOSITION_PROFILE]},
            "url": f"{self.base_url}/Composition/{comp_id}",
            "identifier": {
                "system": self.base_url,
                "value": to_fhir_id(self.fhir_form_id, "composition"),
            },
            "status": "preliminary",
            "type": {
                "coding": [
                    {
                        "system": "http://hl7.org/fhir/ValueSet/doc-typecodes",
                        "code": "57016-8",
                        "display": "Privacy policy acknowledgement Document",
                    }
                ]
            },
            "date": self._today_str(),
            "author": [{"display": "TRICC OpenSRPStrategy"}],
            "title": f"{form_label} Configuration Package",
            "section": sections,
        }

    # ── Questionnaire wiring ──────────────────────────────────────────────────

    def _wire_questionnaire_extensions(self, process: str, pd: dict, version: str):
        """Add cqlInputResources and planDefinitions extensions to a Questionnaire.

        Args:
            process: The cpg-common-process name.
            pd: The PlanDefinition resource dict for this process.
            version: Build version string.
        """
        q = self.questionnaires.get(process)
        if q is None:
            return

        lib_id = self._process_resource_ids(process)["lib_id"]
        lib_url = f"{self.base_url}/Library/{lib_id}"
        pd_url = f"{self.base_url}/PlanDefinition/{pd['id']}"

        extensions = q.setdefault("extension", [])

        # cqlInputResources
        extensions.append({
            "url": FHIRCORE_EXT_CQL_INPUT,
            "valueReference": {"reference": lib_url},
        })

        # planDefinitions
        extensions.append({
            "url": FHIRCORE_EXT_PLAN_DEFINITIONS,
            "valueReference": {"reference": pd_url},
        })

        extract_sm = (self.extraction_maps or {}).get(process)
        if isinstance(extract_sm, dict) and extract_sm.get("url"):
            extensions.append(target_structuremap_extension(extract_sm["url"]))

    # ── File writers ──────────────────────────────────────────────────────────

    def _clean_stale_package_files(self, base: Path) -> None:
        """Remove prior export artifacts so UUID-named files do not linger.

        Filenames are human-readable; REST ``id`` is only inside JSON. Cleaning
        avoids push scripts uploading obsolete UUID-stem files from older runs.

        Args:
            base: Package root ``output/<form_id>/``.
        """
        for sub in (
            "plan-definition",
            "structure-map",
            "binary",
            "questionnaire",
            "library",
        ):
            d = base / sub
            if not d.is_dir():
                continue
            for f in d.iterdir():
                if f.is_file() and f.suffix in {".json", ".map", ".cql"}:
                    try:
                        f.unlink()
                    except OSError as exc:
                        logger.warning("Could not remove stale file %s: %s", f, exc)
        # Legacy flat layout (pre-subfolder questionnaire/library)
        for pattern in (
            "Library-*.json",
            "Questionnaire-*.json",
            "Composition.json",
            "*.cql",
            "*.map",
        ):
            for f in base.glob(pattern):
                if f.is_file():
                    try:
                        f.unlink()
                    except OSError as exc:
                        logger.warning("Could not remove stale file %s: %s", f, exc)
        # Stale UUID-stem JSON left at package root from earlier builds
        import re

        uuid_stem = re.compile(
            r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}\.json$",
            re.I,
        )
        for f in base.glob("*.json"):
            if uuid_stem.match(f.name):
                try:
                    f.unlink()
                    logger.info("Removed stale UUID-named export file %s", f.name)
                except OSError as exc:
                    logger.warning("Could not remove stale file %s: %s", f, exc)

    def _write_plan_definitions(self, base: Path, version: str):
        """Write PlanDefinition JSON with readable filenames (UUID stays in ``id``).

        Args:
            base: Base output directory path.
            version: Build version string.
        """
        pd_dir = base / "plan-definition"
        pd_dir.mkdir(parents=True, exist_ok=True)
        for process, pd in self.plan_definitions.items():
            fname = readable_resource_filename(
                pd, prefix="PlanDefinition", fallback=f"{process}-PD"
            )
            path = pd_dir / fname
            path.write_text(json.dumps(pd, indent=2, ensure_ascii=False))
            logger.debug(f"Wrote PlanDefinition: {path} (id={pd.get('id')})")

    def _write_structure_maps(self, base: Path):
        """Write Task StructureMap JSON (+ companion .map FML) under structure-map/.

        Filenames are human-readable; JSON ``id`` is the UUID used by push.

        Args:
            base: Base output directory path.
        """
        if not self.structuremaps:
            return
        sm_dir = base / "structure-map"
        sm_dir.mkdir(parents=True, exist_ok=True)
        for process, sm in self.structuremaps.items():
            # Strip private helper keys before JSON serialization
            payload = {k: v for k, v in sm.items() if not k.startswith("_")}
            fname = readable_resource_filename(
                sm, prefix="StructureMap", fallback=f"{process}-task"
            )
            path = sm_dir / fname
            path.write_text(json.dumps(payload, indent=2, ensure_ascii=False))
            logger.debug(f"Wrote StructureMap: {path} (id={sm.get('id')})")
            fml = sm.get("_fml")
            if fml:
                map_stem = fname[: -len(".json")] if fname.endswith(".json") else fname
                map_path = sm_dir / f"{map_stem}.map"
                map_path.write_text(fml)
                logger.debug(f"Wrote StructureMap FML: {map_path}")

    def _copy_push_scripts(self, base: Path):
        """Copy FHIR push helper + env template + Postman helpers into the export package root.

        Templates live under ``strategies/output/templates/opensrp/`` and are
        copied next to the generated JSON so deployers can run::

            # .env is created once from env.fhir.example if missing
            ./push-to-fhir.sh

        or import ``push-to-fhir.postman_collection.json`` /
        ``push-to-fhir.postman_environment.json`` into Postman for the same
        auth + PUT calls done manually / one resource at a time.

        ``push-to-fhir.sh``, ``env.fhir.example``, and the Postman collection/
        environment are always refreshed from the package templates. ``.env``
        is only written when it does **not** already exist (preserves local
        URL/credentials across re-exports).

        Args:
            base: Base output directory path (``output/<form_id>/``).
        """
        templates = Path(__file__).resolve().parent / "templates" / "opensrp"
        if not templates.is_dir():
            logger.warning("OpenSRP push templates missing at %s", templates)
            return

        # Always refresh the push script, the example template, and the Postman helpers
        for name in (
            "push-to-fhir.sh",
            "compile-structuremap.sh",
            "CompileStructureMap.java",
            "env.fhir.example",
            "push-to-fhir.postman_collection.json",
            "push-to-fhir.postman_environment.json",
        ):
            src = templates / name
            if not src.is_file():
                logger.warning("Missing template %s", src)
                continue
            dest = base / name
            shutil.copy2(src, dest)
            if name.endswith(".sh"):
                mode = dest.stat().st_mode
                dest.chmod(mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)
            logger.debug("Copied %s → %s", src.name, dest)

        # Seed .env only once — never overwrite existing credentials
        env_example = base / "env.fhir.example"
        env_dest = base / ".env"
        if env_example.is_file() and not env_dest.exists():
            shutil.copy2(env_example, env_dest)
            logger.info("OpenSRPStrategy: created %s from env.fhir.example", env_dest)
        elif env_dest.exists():
            logger.debug("OpenSRPStrategy: leaving existing %s unchanged", env_dest)

        logger.info(
            "OpenSRPStrategy: push helpers at %s/push-to-fhir.sh "
            "(edit .env / .secrets; .env is not overwritten on re-export)",
            base,
        )

    def _write_related_person_contract(self, base: Path):
        """Write RelatedPerson contract JSON for registration / StructureMap authors.

        Args:
            base: Base output directory path.
        """
        form_label = getattr(self, "_form_id", None) or self.fhir_form_id
        # Plain JSON only (not pushed to FHIR). Basic was often 403 on openSRP gateways.
        out_dir = base / "contract"
        out_dir.mkdir(parents=True, exist_ok=True)
        plain = {
            **RELATED_PERSON_CONTRACT,
            "form_id": form_label,
            "structure_map_hints": structure_map_related_person_hints(),
            "example": {
                "resourceType": "RelatedPerson",
                "note": "patient always = child; identifier PI = parent Patient URL",
            },
        }
        path = out_dir / "related-person-contract.json"
        path.write_text(json.dumps(plain, indent=2, ensure_ascii=False))
        logger.debug(f"Wrote RelatedPerson contract: {path}")

    def _write_composition(self, base: Path):
        """Write the Composition JSON file (readable name; UUID in ``id``).

        Args:
            base: Base output directory path.
        """
        if self.composition:
            fname = readable_resource_filename(
                self.composition, fallback="composition"
            )
            # Prefer stable package-root name for the manifest
            path = base / "Composition.json"
            path.write_text(
                json.dumps(self.composition, indent=2, ensure_ascii=False)
            )
            logger.debug(
                "Wrote Composition: %s (id=%s, logical=%s)",
                path,
                self.composition.get("id"),
                fname,
            )

    def _write_image_binaries(self, base: Path):
        """Write per-image Binary resources referenced by itemMedia/itemAnswerMedia.

        Populated by ``FHIRStrategy._register_image_binary`` while walking the
        graph (one Binary per distinct image file); already listed in the
        Composition's "Binaries" section via ``self.binaries``.

        Args:
            base: Base output directory path.
        """
        if not self.binaries:
            return
        bin_dir = base / "binary"
        bin_dir.mkdir(parents=True, exist_ok=True)
        for binary in self.binaries:
            fname = readable_resource_filename(
                binary, prefix="Binary", fallback=binary.get("id", "image")
            )
            path = bin_dir / fname
            path.write_text(json.dumps(binary, indent=2, ensure_ascii=False))
            logger.debug("Wrote image Binary: %s (id=%s)", path, binary.get("id"))

    # ── Utilities ─────────────────────────────────────────────────────────────

    def _app_id_coding(self) -> dict:
        """Return the Coding used as ``meta.tag`` for this app package."""
        return {
            "system": APP_ID_TAG_SYSTEM,
            "code": self.app_id,
            "display": f"{self.app_id} application package",
        }

    def stamp_app_id_tag(self, resource: Optional[dict]) -> Optional[dict]:
        """Ensure ``resource.meta.tag`` includes the app-id Coding (idempotent).

        Package Compositions keep their own ``identifier`` (tricc system) and
        must **not** use shell app-id as Composition.identifier — only meta.tag.

        Args:
            resource: FHIR resource dict (mutated in place).

        Returns:
            The same resource dict, or ``None`` if input was ``None``.
        """
        if not isinstance(resource, dict) or not resource.get("resourceType"):
            return resource
        meta = resource.setdefault("meta", {})
        if not isinstance(meta, dict):
            resource["meta"] = {"tag": [self._app_id_coding()]}
            return resource
        tags = meta.setdefault("tag", [])
        if not isinstance(tags, list):
            meta["tag"] = [self._app_id_coding()]
            return resource
        coding = self._app_id_coding()
        for t in tags:
            if (
                isinstance(t, dict)
                and t.get("system") == coding["system"]
                and t.get("code") == coding["code"]
            ):
                return resource
        tags.append(coding)
        return resource

    def ensure_opensrp_questionnaire_fields(self, q: Optional[dict]) -> Optional[dict]:
        """Make Questionnaire compatible with openSRP QuestionnaireActivity.

        openSRP refuses to open a form without ``Questionnaire.subjectType``
        (toast: "Missing subject type on questionnaire…"). Client interventions
        are always subject = Patient.

        Also normalizes ``status`` / ``experimental`` for runtime launch.

        Args:
            q: Questionnaire resource dict.

        Returns:
            The same dict (mutated), or ``None``.
        """
        if not isinstance(q, dict) or q.get("resourceType") != "Questionnaire":
            return q
        # FHIR R4: subjectType is code array, e.g. ["Patient"]
        st = q.get("subjectType")
        if not st:
            q["subjectType"] = ["Patient"]
        elif isinstance(st, list) and "Patient" not in st:
            q["subjectType"] = list(st) + ["Patient"]
        elif isinstance(st, str) and st != "Patient":
            q["subjectType"] = [st, "Patient"]
        # Prefer active for forms launched from Start care
        if q.get("status") in (None, "", "draft", "preliminary"):
            q["status"] = "active"
        if q.get("experimental") is True:
            q["experimental"] = False
        return q

    def _stamp_package_app_id_tags(self) -> None:
        """Stamp app-id meta.tag and openSRP-required Questionnaire fields."""
        for q in (self.questionnaires or {}).values():
            self.ensure_opensrp_questionnaire_fields(q)
            self.stamp_app_id_tag(q)
        for lib in (getattr(self, "libraries", None) or {}).values():
            self.stamp_app_id_tag(lib)
        for sm in list((self.structuremaps or {}).values()) + list((self.extraction_maps or {}).values()):
            # structuremaps may carry private _fml key; still a dict with resourceType
            if isinstance(sm, dict) and sm.get("resourceType") == "StructureMap":
                self.stamp_app_id_tag(sm)
        for vs in (getattr(self, "valuesets", None) or {}).values():
            self.stamp_app_id_tag(vs)
        for pd in (self.plan_definitions or {}).values():
            self.stamp_app_id_tag(pd)
            # Contained ActivityDefinitions are not synced by id; tag parent PD only
        for binary in self.binaries:
            if isinstance(binary, dict) and binary.get("resourceType") == "Binary":
                self.stamp_app_id_tag(binary)
        if self.composition:
            self.stamp_app_id_tag(self.composition)
        logger.info(
            "OpenSRPStrategy: stamped meta.tag %s|%s and Questionnaire.subjectType=Patient",
            APP_ID_TAG_SYSTEM,
            self.app_id,
        )

    @staticmethod
    def _today_str() -> str:
        """Return today's date as an ISO 8601 string.

        Returns:
            Date string in ``YYYY-MM-DD`` format.
        """
        import datetime
        return datetime.date.today().isoformat()


def _xml_escape(text: str) -> str:
    """Escape text for embedding inside XHTML narrative.

    Args:
        text: Raw text (e.g. FML source).

    Returns:
        XML-escaped string.
    """
    return (
        text.replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
    )
