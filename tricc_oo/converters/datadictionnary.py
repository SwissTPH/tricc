from fhir.resources.codesystem import (
    CodeSystem,
    CodeSystemConcept,
    CodeSystemConceptDesignation,
    CodeSystemConceptProperty,
)
from fhir.resources.coding import Coding
from tricc_oo.visitors.text_injection import serialize_injection_for_js_text

from fhir.resources.valueset import ValueSet
import logging
import uuid

logger = logging.getLogger("default")

# Namespace for deterministic UUIDs
UUID_NAMESPACE = uuid.UUID('12345678-1234-5678-9abc-def012345678')

# CodeSystem concept.designation[].use for the texts of a concept: the label uses the
# HL7 designation-usage code (as tricc_og writes it), hint / help a TRICC system.
DESIGNATION_USAGE_SYSTEM = "http://terminology.hl7.org/CodeSystem/designation-usage"
TRICC_DESIGNATION_USE_SYSTEM = "https://tricc.org/CodeSystem/designation-use"
DESIGNATION_USES = {
    "display": (DESIGNATION_USAGE_SYSTEM, "display"),
    "hint": (TRICC_DESIGNATION_USE_SYSTEM, "hint"),
    "help": (TRICC_DESIGNATION_USE_SYSTEM, "help"),
}


def designation_use(designation):
    """'display' / 'hint' / 'help' for a designation (no ``use`` counts as display), else None."""
    use = getattr(designation, "use", None)
    if use is None:
        return "display"
    for key, (system, code) in DESIGNATION_USES.items():
        if use.code == code and (use.system or system) == system:
            return key
    return None


def get_designation(concept, use, language):
    """Value of the ``use`` designation of ``concept`` in ``language``, or None."""
    for designation in getattr(concept, "designation", None) or []:
        if designation.language == language and designation_use(designation) == use:
            return designation.value
    return None


def add_designation(concept, use, language, value):
    """Add a ``use`` designation unless one already exists for that language."""
    if not value or not language or get_designation(concept, use, language) is not None:
        return False
    system, code = DESIGNATION_USES[use]
    designation = CodeSystemConceptDesignation(
        language=language, use=Coding(system=system, code=code), value=value
    )
    if not getattr(concept, "designation", None):
        concept.designation = []
    concept.designation.append(designation)
    return True


def lookup_codesystems_code(codesystems, ref):
    if ref.startswith("final."):
        concept = lookup_codesystems_code(codesystems, ref[6:])
        if concept:
            return concept
    for code_system in codesystems.values():
        for concept in code_system.concept or []:
            if concept.code == ref:
                return concept


def add_concept(codesystems, system, code, display, attributes, terminology=None):
    """Add (or merge into) ``system|code``.

    ``terminology`` holds the ``(system, code)`` pairs loaded from the tricc.yaml
    ``terminology``: their CodeSystem text wins quietly over the authored one.
    """
    if system and system not in codesystems:
        logger.info(f"New codesystem {system} added to project")
        codesystems[system] = init_codesystem(system, system)

    quiet = bool(terminology) and (system, code) in terminology
    return check_and_add_concept(codesystems[system], code, display, attributes, quiet=quiet)


def add_concept_texts(concept, language, hint=None, help=None):
    """Store an authored node's hint / help as designations of its concept (gaps only)."""
    for use, value in (("hint", hint), ("help", help)):
        if value is not None:
            add_designation(concept, use, language, serialize_injection_for_js_text(value).strip())


def init_codesystem(code, name):
    return CodeSystem(
        id=code.replace("_", "-"),
        url=f"http://example.com/fhir/CodeSystem/{code}",
        version="1.0.0",
        name=name,
        title=name,
        status="draft",
        description=f"Code system for {name}",
        content="complete",
        concept=[],
    )


def init_valueset(code, name):
    return ValueSet(
        id=code,
        url=f"http://example.com/fhir/ValueSet/{code}",
        version="1.0.0",
        name=name,
        title=name,
        status="draft",
        description=f"Valueset for {name}",
        content="complete",
        conatains=[],
    )


def check_and_add_concept(code_system: CodeSystem, code: str, display: str, attributes: dict = {}, quiet=False):
    """
    Checks if a concept with the given code already exists in the CodeSystem.
    If it exists, it is kept (a differing display is a warning, or a debug message when
    ``quiet``, i.e. the concept comes from the project terminology). Otherwise, adds the concept.

    Args:
        code_system (CodeSystem): The CodeSystem to check and update.
        code (str): The code of the concept to add.
        display (str): The display of the concept to add.
            May also be a parsed injection (TriccOperation / TriccReference);
            it is serialized to JS/ODK text before storage and comparison.
    """
    display_text = serialize_injection_for_js_text(display)
    new_concept = None
    # Check if the concept already exists
    for concept in code_system.concept or []:
        if concept.code == code:
            existing_display = concept.display or ""
            if existing_display.lower() != display_text.lower():
                (logger.debug if quiet else logger.warning)(
                    f"""Code {code} already exists with a different display:
                    Concept:{existing_display}\n Current:{display_text}"""
                )
            new_concept = concept
    if not new_concept:
        # Add the new concept if it does not exist
        concept_id = str(uuid.uuid5(UUID_NAMESPACE,(code)))
        new_concept = CodeSystemConcept.construct(code=code, display=display_text, id=concept_id)
        if not hasattr(code_system, "concept"):
            code_system.concept = []
        code_system.concept.append(new_concept)

    if attributes and not new_concept.property:
        new_concept.property = []

    for k, v in attributes.items():
        existing_attributes = False
        for p in new_concept.property:
            if p.code == k:
                # TODO support other type of Codesystem Concept Property Value
                existing_attributes = True
                if p.valueString != v:
                    (logger.debug if quiet else logger.warning)(
                        f"conflicting value for concept `{new_concept.code}` property ` {k}`: {p.valueString} != {v}"
                    )
        if not existing_attributes:
            new_concept.property.append(CodeSystemConceptProperty(code=k, valueString=v))

    return new_concept
