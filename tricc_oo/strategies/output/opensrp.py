"""
OpenSRPStrategy: openSRP / fhircore-specific FHIR export strategy for TRICC.

Extends ``FHIRStrategy`` with:
- FHIR PlanDefinition (one per process, cpg-common-process triggers)
- Top-level Composition resource (fhircore config manifest)
- Binary config package resource
- openSRP profile references on all resources
- ``cqlInputResources`` and ``planDefinitions`` wiring on Questionnaires
- FSH files for every resource

Output folder structure (matches fhircore expected layout):
    output/<form_id>/
    ├── Composition.json
    ├── questionnaire/
    ├── plan-definition/
    ├── library/
    ├── structure-map/
    ├── binary/
    ├── ValueSet/
    └── fsh/

Usage::

    tricc -i input.drawio -o output/ -O OpenSRPStrategy
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Dict, List, Optional

from tricc_oo.converters.fhir.fsh_serializer import resource_to_fsh
from tricc_oo.strategies.output.fhir_form import (
    DEFAULT_BASE_URL,
    FHIR_VERSION,
    FHIRStrategy,
)
from tricc_oo.visitors.utils import PROCESSES

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


class OpenSRPStrategy(FHIRStrategy):
    """openSRP / fhircore output strategy.

    Inherits all standard FHIR SDC generation from ``FHIRStrategy`` and adds
    openSRP-specific resources: PlanDefinition, Composition manifest, Binary
    config package, and FSH files.

    Attributes:
        plan_definitions: Dict mapping process name → PlanDefinition resource dict.
        composition: The top-level Composition resource dict (built at export time).
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

    # ── Lifecycle override ────────────────────────────────────────────────────

    def execute(self):
        """Run the full openSRP export pipeline.

        Calls the parent FHIR pipeline then adds openSRP-specific resources.
        """
        super().execute()

    def export(self, start_pages, version: str = ""):
        """Write all generated resources to the output directory.

        Extends the parent export with PlanDefinition, Composition, Binary
        config manifest, and FSH files.

        Args:
            start_pages: Dict of start pages from the project.
            version: Build version string.
        """
        base = Path(self.output_path) / self._form_id

        # Build openSRP-specific resources before writing
        for process in list(self.questionnaires.keys()):
            pd = self.generate_plandefinition(process, version)
            self.plan_definitions[process] = pd
            # Wire planDefinitions + cqlInputResources onto the Questionnaire
            self._wire_questionnaire_extensions(process, pd, version)

        self.composition = self.generate_composition(version)

        # Write standard FHIR resources (questionnaire, library, structure-map, ValueSet, binary)
        super().export(start_pages, version)

        # Write openSRP-specific resources
        self._write_plan_definitions(base, version)
        self._write_composition(base)
        self._write_binary_config(base, version)
        self._write_fsh_files(base, version)

        logger.info(f"OpenSRPStrategy: exported openSRP package to {base}")

    def validate(self):
        """Validate the generated openSRP resources.

        Raises:
            Warning logs for any detected issues.
        """
        super().validate()
        for process, pd in self.plan_definitions.items():
            if not pd.get("action"):
                logger.warning(f"PlanDefinition for process '{process}' has no actions")
        if self.composition is None:
            logger.warning("Composition resource was not generated")
        logger.info("OpenSRPStrategy: openSRP validation complete")

    # ── openSRP resource generators ───────────────────────────────────────────

    def generate_plandefinition(self, process: str, version: str) -> dict:
        """Build a PlanDefinition resource for a process.

        Uses cpg-common-process named triggers as required by fhircore.

        Args:
            process: The cpg-common-process name (e.g. ``"registration"``).
            version: Build version string.

        Returns:
            PlanDefinition resource dict.
        """
        pd_id = f"{self._form_id}-{process}-PD"
        q_id = f"{self._form_id}-{process}"
        lib_id = f"{self._form_id}-{process}"

        # Determine trigger code (use process name if it's a known cpg-common-process)
        trigger_code = process if process in PROCESSES else "registration"

        return {
            "resourceType": "PlanDefinition",
            "id": pd_id,
            "meta": {"profile": [OPENSRP_PLANDEFINITION_PROFILE]},
            "url": f"{self.base_url}/PlanDefinition/{pd_id}",
            "name": pd_id,
            "title": f"{self._form_id} – {process} Plan",
            "version": version or "1.0.0",
            "status": "draft",
            "experimental": True,
            "type": {
                "coding": [
                    {
                        "system": "http://terminology.hl7.org/CodeSystem/plan-definition-type",
                        "code": "clinical-protocol",
                    }
                ]
            },
            "library": [f"{self.base_url}/Library/{lib_id}"],
            "action": [
                {
                    "id": f"action-{process}",
                    "title": f"Launch {process} questionnaire",
                    "trigger": [
                        {
                            "type": "named-event",
                            "name": trigger_code,
                        }
                    ],
                    "condition": [
                        {
                            "kind": "applicability",
                            "expression": {
                                "language": "text/cql-identifier",
                                "expression": "Is Applicable",
                                "reference": f"{self.base_url}/Library/{lib_id}",
                            },
                        }
                    ],
                    "definitionCanonical": f"{self.base_url}/Questionnaire/{q_id}",
                }
            ],
        }

    def generate_composition(self, version: str) -> dict:
        """Build the top-level Composition resource (fhircore config manifest).

        The Composition references all generated resources as required by the
        fhircore configuration model.

        Args:
            version: Build version string.

        Returns:
            Composition resource dict.
        """
        comp_id = f"{self._form_id}-composition"
        sections = []

        # Questionnaires section
        q_entries = [
            {"reference": f"Questionnaire/{q['id']}"}
            for q in self.questionnaires.values()
        ]
        if q_entries:
            sections.append({
                "title": "Questionnaires",
                "code": {
                    "coding": [{"system": "http://hl7.org/fhir/resource-types", "code": "Questionnaire"}]
                },
                "entry": q_entries,
            })

        # PlanDefinitions section
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

        # Libraries section
        lib_entries = [
            {"reference": f"Library/{self._form_id}Helper"},
        ] + [
            {"reference": f"Library/{self._form_id}-{process}"}
            for process in self.questionnaires
        ]
        if lib_entries:
            sections.append({
                "title": "Libraries",
                "code": {
                    "coding": [{"system": "http://hl7.org/fhir/resource-types", "code": "Library"}]
                },
                "entry": lib_entries,
            })

        # StructureMaps section
        sm_entries = [
            {"reference": f"StructureMap/{sm['id']}"}
            for sm in self.structuremaps.values()
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
                "value": comp_id,
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
            "title": f"{self._form_id} Configuration Package",
            "section": sections,
        }

    def generate_binary_config(self, version: str) -> dict:
        """Build a Binary resource containing the full config package as JSON.

        Args:
            version: Build version string.

        Returns:
            Binary resource dict.
        """
        import base64 as _b64

        config_payload = {
            "version": version,
            "form_id": self._form_id,
            "base_url": self.base_url,
            "processes": list(self.questionnaires.keys()),
            "questionnaires": [q["id"] for q in self.questionnaires.values()],
            "plan_definitions": [pd["id"] for pd in self.plan_definitions.values()],
        }
        payload_bytes = json.dumps(config_payload, indent=2).encode()
        payload_b64 = _b64.b64encode(payload_bytes).decode()

        return {
            "resourceType": "Binary",
            "id": f"{self._form_id}-config",
            "contentType": "application/json",
            "data": payload_b64,
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

        lib_id = f"{self._form_id}-{process}"
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

    # ── File writers ──────────────────────────────────────────────────────────

    def _write_plan_definitions(self, base: Path, version: str):
        """Write PlanDefinition JSON files.

        Args:
            base: Base output directory path.
            version: Build version string.
        """
        pd_dir = base / "plan-definition"
        pd_dir.mkdir(parents=True, exist_ok=True)
        for process, pd in self.plan_definitions.items():
            path = pd_dir / f"{pd['id']}.json"
            path.write_text(json.dumps(pd, indent=2, ensure_ascii=False))
            logger.debug(f"Wrote PlanDefinition: {path}")

    def _write_composition(self, base: Path):
        """Write the Composition JSON file.

        Args:
            base: Base output directory path.
        """
        if self.composition:
            path = base / "Composition.json"
            path.write_text(json.dumps(self.composition, indent=2, ensure_ascii=False))
            logger.debug(f"Wrote Composition: {path}")

    def _write_binary_config(self, base: Path, version: str):
        """Write the Binary config package JSON file.

        Args:
            base: Base output directory path.
            version: Build version string.
        """
        binary_config = self.generate_binary_config(version)
        bin_dir = base / "binary"
        bin_dir.mkdir(parents=True, exist_ok=True)
        path = bin_dir / f"{binary_config['id']}.json"
        path.write_text(json.dumps(binary_config, indent=2, ensure_ascii=False))
        logger.debug(f"Wrote Binary config: {path}")

    def _write_fsh_files(self, base: Path, version: str):
        """Write FSH (FHIR Shorthand) files for all generated resources.

        Args:
            base: Base output directory path.
            version: Build version string.
        """
        fsh_dir = base / "fsh"
        fsh_dir.mkdir(parents=True, exist_ok=True)

        all_resources: List[dict] = []
        all_resources.extend(self.questionnaires.values())
        all_resources.extend(self.plan_definitions.values())
        all_resources.extend(self.structuremaps.values())
        all_resources.extend(self.valuesets.values())
        all_resources.extend(self.binaries)
        if self.composition:
            all_resources.append(self.composition)

        for resource in all_resources:
            resource_type = resource.get("resourceType", "Unknown")
            resource_id = resource.get("id", "unknown")
            try:
                fsh_content = resource_to_fsh(resource)
                path = fsh_dir / f"{resource_type}-{resource_id}.fsh"
                path.write_text(fsh_content)
                logger.debug(f"Wrote FSH: {path}")
            except Exception as exc:
                logger.warning(f"FSH generation failed for {resource_type}/{resource_id}: {exc}")

    # ── Utilities ─────────────────────────────────────────────────────────────

    @staticmethod
    def _today_str() -> str:
        """Return today's date as an ISO 8601 string.

        Returns:
            Date string in ``YYYY-MM-DD`` format.
        """
        import datetime
        return datetime.date.today().isoformat()
