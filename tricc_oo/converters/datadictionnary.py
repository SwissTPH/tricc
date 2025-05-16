from fhir.resources.codesystem import (
    CodeSystem,
    CodeSystemConcept,
    CodeSystemConceptDesignation,
    CodeSystemConceptProperty
)
from fhir.resources.codeableconcept import CodeableConcept
from fhir.resources.range import Range
from fhir.resources.quantity import Quantity
from fhir.resources.coding import Coding

from fhir.resources.valueset import ValueSet, ValueSetCompose, ValueSetComposeInclude
import logging

logger = logging.getLogger("default")


def lookup_codesystems_code(codesystems, ref):
    if ref.startswith('final.'):
        concept = lookup_codesystems_code(codesystems, ref[6:])
        if concept:
            return concept
    for code_system in codesystems.values():
        for concept in code_system.concept or []:
            if concept.code == ref:
                return concept


def add_concept(codesystems, system, code, display, attributes):
    if system and system not in codesystems:
        logger.info(f"New codesystem {system} added to project")
        codesystems[system] = init_codesystem(system, system)
    
    
    
    return check_and_add_concept(codesystems[system], code, display, attributes)
            

                
    
def init_codesystem(code, name):
    return CodeSystem(
            id=code.replace('_','-'),
            url=f"http://example.com/fhir/CodeSystem/{code}",
            version="1.0.0",
            name=name,
            title=name,
            status="draft",
            description=f"Code system for {name}",
            content="complete",
            concept=[]
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
            conatains=[]
        )

def check_and_add_concept(code_system: CodeSystem, code: str, display: str, attributes: dict={}):
    """
    Checks if a concept with the given code already exists in the CodeSystem.
    If it exists with a different display, raises an error. Otherwise, adds the concept.

    Args:
        code_system (CodeSystem): The CodeSystem to check and update.
        code (str): The code of the concept to add.
        display (str): The display of the concept to add.

    Raises:
        ValueError: If a concept with the same code exists but has a different display.
    """
    new_concept = None
    # Check if the concept already exists
    for concept in code_system.concept or []:
        if concept.code == code:
            
            if concept.display.lower() != display.lower():
                logger.warning(
                    f"Code {code} already exists with a different display:\n Concept:{concept.display}\n Current:{display}"
                )
            new_concept = concept
    if not new_concept:
        # Add the new concept if it does not exist
        new_concept = CodeSystemConcept.construct(code=code, display=display)
        if not hasattr(code_system, "concept"):
            code_system.concept = []
        code_system.concept.append(new_concept)
    
    if attributes and not new_concept.property:
        new_concept.property = []
    
    for k,v in attributes.items():          
        existing_attributes = False
        for p in new_concept.property:
            if p.code == k:
                #TODO support other type of Codesystem Concept Property Value
                existing_attributes
                if p.valueString != v:
                    logger.warning(f"conflicting value for property {k}: {p.valueString} != {v}")
        if not existing_attributes:
            new_concept.property.append(
                CodeSystemConceptProperty(
                    code=k,
                    valueString=v
                )
            )
    
    return new_concept


    return value_set