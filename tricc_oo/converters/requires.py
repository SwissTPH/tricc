"""Prerequisites gathered earlier in the same encounter (``requires``).

An intervention lists the interventions it requires (tricc.yaml ``requires``) and an
activity the concepts it requires (``requires`` in its YAML). Each required concept the
intervention references becomes an **encounter read**: a ``TriccNodePopulate`` with
``context="encounter"`` named by the concept and hung on the start page, so it is the first
version of the concept; a node of the intervention with the same name is a later version.
See feature/20261125-requires-and-implied-retrievals.md §1, §2.
"""

from __future__ import annotations

import logging
from typing import Any, Iterable, List, Optional, Set

logger = logging.getLogger("default")

E_REQUIRES_UNKNOWN = "E_REQUIRES_UNKNOWN"


class TriccRequiresError(ValueError):
    """A ``requires`` entry naming no project intervention or concept.

    Attributes:
        code: The error code (``E_REQUIRES_UNKNOWN``).
    """

    def __init__(self, code: str, message: str):
        super().__init__(f"{code}: {message}")
        self.code = code
        self.message = message


def check_intervention_requires(interventions: Iterable[Any]) -> None:
    """Every intervention ``requires`` entry must be the id of a project intervention.

    Args:
        interventions: The tricc.yaml ``interventions`` (``TriccInterventionConfig``).

    Raises:
        TriccRequiresError: ``E_REQUIRES_UNKNOWN`` for an entry that is not an intervention id.
    """
    interventions = list(interventions)
    ids = {item.id for item in interventions}
    for item in interventions:
        for entry in item.requires or []:
            if not isinstance(entry, str) or entry not in ids:
                raise TriccRequiresError(
                    E_REQUIRES_UNKNOWN,
                    f"intervention {item.id!r} requires {entry!r}, which is not an intervention id "
                    f"({', '.join(sorted(ids))})",
                )


def activity_required_concept(entry: Any, code_systems, where: str) -> str:
    """The code of one activity ``requires`` entry (code or ``{system, code}``).

    Args:
        entry: The entry as written.
        code_systems: The project CodeSystems (``project.code_systems``).
        where: The activity, for the error.

    Returns:
        The concept code.

    Raises:
        TriccRequiresError: ``E_REQUIRES_UNKNOWN`` when the entry is not a project concept.
    """
    from tricc_oo.converters.datadictionnary import find_concept

    if isinstance(entry, str):
        code, system = entry, None
    elif isinstance(entry, dict):
        code, system = entry.get("code"), entry.get("system")
    else:
        code, system = getattr(entry, "code", None), getattr(entry, "system", None)
    if not code or not code_systems or find_concept(code_systems, code, system) is None:
        raise TriccRequiresError(E_REQUIRES_UNKNOWN, f"{where} requires {entry!r}, which is not a project concept")
    return code


def provided_concepts(project) -> Set[str]:
    """Concepts the loaded activities of ``project`` record: inputs and persisted calculates.

    A calculate is persisted when the FHIR extraction would record it
    (``concept_mapper.classify_extraction``); populate reads and retrievals never are.
    """
    from tricc_oo.converters.fhir.concept_mapper import classify_extraction
    from tricc_oo.models.calculate import TriccNodePopulate
    from tricc_oo.models.tricc import TriccNodeCalculateBase, TriccNodeInputModel

    found: Set[str] = set()
    for page in (getattr(project, "pages", None) or {}).values():
        for node in (getattr(page, "nodes", None) or {}).values():
            name = getattr(node, "name", None)
            if not name or isinstance(node, TriccNodePopulate):
                continue
            if isinstance(node, TriccNodeInputModel):
                found.add(name)
            elif isinstance(node, TriccNodeCalculateBase) and classify_extraction(
                node, getattr(project, "code_systems", None)
            ):
                found.add(name)
    return found


def referenced_names(project) -> Set[str]:
    """Names the loaded pages and library calculates reference (not retrievals)."""
    from tricc_oo.converters.retrieval import expression_nodes, reference_values

    found: Set[str] = set()
    for value in expression_nodes(project):
        reference_values(value, found)
    return {name for name in found if not name.startswith("#")}


def build_required_reads(project) -> List[Any]:
    """One encounter read per required concept the intervention references (once per project).

    Fills ``project.required_read_nodes``.
    """
    if getattr(project, "required_read_nodes", None):
        return project.required_read_nodes
    required = set(getattr(project, "required_concepts", None) or ()) | set(
        getattr(project, "activity_requires", None) or ()
    )
    if not required:
        return []
    used = sorted(required & referenced_names(project))
    project.required_read_nodes = [build_encounter_read(code, project) for code in used]
    if used:
        logger.info(f"required concepts read from the encounter: {', '.join(used)}")
    return project.required_read_nodes


def build_encounter_read(code: str, project=None):
    """The ``TriccNodePopulate`` (``context="encounter"``) reading ``code`` from the encounter."""
    from tricc_oo.converters.datadictionnary import find_concept
    from tricc_oo.converters.retrieval import _data_type_to_item, _property_text
    from tricc_oo.converters.utils import generate_id
    from tricc_oo.models.calculate import TriccNodePopulate

    concept: Optional[Any] = None
    code_systems = getattr(project, "code_systems", None)
    if code_systems:
        concept = find_concept(code_systems, code, None)
    return TriccNodePopulate(
        id=generate_id(f"requires:{code}"),
        name=code,
        label=(getattr(concept, "display", None) or code),
        context="encounter",
        source=code,
        concept_type=_property_text(concept, "conceptType") if concept is not None else None,
        data_type=_data_type_to_item(_property_text(concept, "dataType")) if concept is not None else None,
    )
