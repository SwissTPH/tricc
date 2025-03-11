from typing import Dict, List, Any
import json
from fhir.resources.codesystem import CodeSystem
from tricc_oo.models.ocl import (
    OCLConcept,
    OCLSource,
    OCLDetailedName,
    OCLDetailedDescription,
    OclConstants,
    get_data_type
)

def extract_properties_metadata(fhir_cs: CodeSystem) -> Dict[str, Dict]:
    """
    Extracts property definitions from FHIR CodeSystem and converts them to OCL attribute types
    """
    property_types = {}
    if hasattr(fhir_cs, 'property') and fhir_cs.property:
        for prop in fhir_cs.property:
            # Map FHIR property types to OCL datatypes
            fhir_type = prop.type
            ocl_type = {
                "code": "Text",
                "Coding": "Concept",
                "boolean": "Boolean",
                "decimal": "Numeric",
                "integer": "Numeric",
                "dateTime": "DateTime",
                "string": "Text"
            }.get(fhir_type, "Text")
            
            property_types[prop.code] = {
                "name": prop.code,
                "datatype": ocl_type,
                "description": prop.description if hasattr(prop, 'description') else ""
            }
    return property_types

def get_fhir_concept_datatype(concept):
    
    datatype = extract_concept_properties(concept, ['datatype'])
    if datatype:
        return datatype['datatype']
    else:
        return OclConstants.DATA_TYPE_NONE

def extract_concept_properties(concept, property_types: List) -> List[Dict]:
    """
    Extracts properties from a FHIR concept and converts them to OCL attributes
    """
    properties = {}
    if hasattr(concept, 'property') and concept.property:
        for prop in concept.property:
            if prop.code in property_types:
                # Handle different property value types
                if getattr(prop, 'valueCode', None):
                    value = prop.valueCode
                elif getattr(prop, 'valueCoding', None):
                    value = prop.valueCoding.code
                elif getattr(prop, 'valueString', None):
                    value = prop.valueString
                elif getattr(prop, 'valueBoolean', None):
                    value = prop.valueBoolean
                elif getattr(prop, 'valueInteger', None):
                    value = prop.valueInteger
                elif getattr(prop, 'valueDecimal', None):
                    value = prop.valueDecimal
                elif getattr(prop, 'valueDateTime', None):
                    value = prop.valueDateTime
                else:
                    continue
                if value:
                    properties[prop.code] = value
    return properties
                
                
def get_attributes_from_concept_properties(concept, property_types: Dict) -> List[Dict]:
    attributes = []
    properties = extract_concept_properties(concept, property_types=list(property_types))
    for code, value in properties.items():
        attributes.append({
            "type": "Attribute",
            "attribute_type": code,
            "value": value,
            "value_type": property_types[code]["datatype"]
        })
    return attributes

def transform_fhir_to_ocl(fhir_codesystem_json: Dict, source_name: str, source_owner: str, source_owner_type: str) -> List[Dict[str, Any]]:
    """
    Transforms a FHIR CodeSystem resource into an OCL bulk upload JSON payload.
    
    Args:
        fhir_codesystem_json: JSON representation of the FHIR CodeSystem resource
        source_name: Name of the OCL Source
        source_owner: Owner of the OCL Source (organization or user)
        source_owner_type : User or Organization
    
    Returns:
        List of dictionaries representing OCL bulk upload format
    """
    # Load the FHIR CodeSystem
    fhir_cs = CodeSystem.parse_obj(fhir_codesystem_json)

    # Extract property definitions
    property_types = extract_properties_metadata(fhir_cs)

    # Initialize OCL payload
    ocl_payload = []

    # Add source metadata

    
    # Add property definitions to extras
    if property_types:
        source_extras["attribute_types"] = list(property_types.values())

    ocl_payload.append(
        OCLSource(
            short_code=source_name,
            id=source_name,
            canonical_url=fhir_cs.url,
            owner=source_owner,
            owner_type=source_owner_type,
            name=fhir_cs.name or "Unnamed Source",
            full_name=fhir_cs.title if hasattr(fhir_cs, 'title') else fhir_cs.name,
            description=fhir_cs.description or "",
            source_type="Dictionary",
            default_locale="en",
            supported_locales=["en"],
        )
      )

    # Transform concepts
    if hasattr(fhir_cs, 'concept') and fhir_cs.concept:
        for concept in fhir_cs.concept:
            datatype = get_fhir_concept_datatype(concept)
            ocl_concept = OCLConcept(
                id=concept.code,
                concept_class="Misc",
                datatype=datatype,
                owner=source_owner,  # Added owner
                owner_type=source_owner_type,
                source=source_name,  # Added source
                names=[
                    OCLDetailedName(
                        name=concept.display,
                        locale="en",
                        name_type=OclConstants.NAME_TYPE_FULLY_SPECIFIED,
                    )
                ],
                descriptions=[]
            )

            # Add definition if present
            if hasattr(concept, 'definition') and concept.definition:
                ocl_concept.descriptions.append(OCLDetailedDescription(
                    description=concept.definition,
                    locale="en",
                ))

            # Extract and add properties as attributes
            attributes = get_attributes_from_concept_properties(concept, property_types)
            if attributes:
                ocl_concept["attributes"] = attributes

            ocl_payload.append(ocl_concept)

    return ocl_payload
