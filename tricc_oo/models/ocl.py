# https://docs.openconceptlab.org/

from enum import Enum
from typing import Dict, List, Optional,  Union, Literal, Annotated
from xml.dom import HIERARCHY_REQUEST_ERR
from xmlrpc.client import Boolean
from pydantic import BaseModel, constr, AnyHttpUrl, StringConstraints
from ocldev.oclconstants import OclConstants, OclConstants as OclConstantsBase

OCLId = Annotated[
    str,
    StringConstraints(pattern=r"^.+$")
]
OCLName = Annotated[
    str,
    StringConstraints(pattern=r"^.+$")
]
OCLShortName = Annotated[
    str,
    StringConstraints(pattern=r"^.+$")
]
OCLLocale = Annotated[
    str,
    StringConstraints(pattern=r"^[a-zA-Z\-]{2,7}$")
]
Uri = Annotated[
    str,
    StringConstraints(pattern=r"^.+$")
]
OCLMapCode = Annotated[
    str,
    StringConstraints(pattern=r"^.+$")
]



class OclConstants(OclConstantsBase):
    #OCL Access type
    ACCESS_TYPE_VIEW = 'View'
    ACCESS_TYPE_EDIT = 'Edit'
    ACCESS_TYPE_NONE = 'None'
    ACCESS_TYPES = [
        ACCESS_TYPE_EDIT,
        ACCESS_TYPE_VIEW,
        ACCESS_TYPE_NONE
    ]
    #https://www.hl7.org/fhir/valueset-codesystem-hierarchy-meaning.html
    HIERARCHY_MEANING_IS_A = 'is-a' 
    HIERARCHY_MEANING_GROUP_BY = 'grouped-by'
    HIERARCHY_MEANING_PART_OF = 'part-of'
    HIERARCHY_MEANING_CLASSIFIED_WITH = ' classified-with'
    HIERARCHY_MEANINGS = [
        HIERARCHY_MEANING_IS_A,
        HIERARCHY_MEANING_GROUP_BY,
        HIERARCHY_MEANING_PART_OF,
        HIERARCHY_MEANING_CLASSIFIED_WITH
    ]
    SOURCE_TYPE_DICTIONARY = "Dictionary"
    SOURCE_TYPE_REFERENCE = "Reference"
    SOURCE_TYPE_EXTERNAL_DICTIONARY = "ExternalDictionary"
    SOURCE_TYPES = [
        SOURCE_TYPE_DICTIONARY,
        SOURCE_TYPE_REFERENCE,
        SOURCE_TYPE_EXTERNAL_DICTIONARY 
    ]
    # MAP type found for fever/malaria on OCL app
    MAP_TYPE_SAME_AS = "SAME-AS"
    MAP_TYPE_PART_OF = "PART-OF"
    MAP_TYPE_Q_AND_A = "Q-AND-A"
    MAP_TYPE_NARROWER_THAN = "NARROWER-THAN"
    MAP_TYPE_CONCEPT_SET = "CONCEPT-SET"
    MAP_TYPE_SYSTEM = "SYSTEM"
    MAP_TYPE_BROADER_THAN = "BROADER-THAN"
    MAP_TYPE_HAS_ANSWER = "HAS-ANSWER"
    MAP_TYPE_HAS_ELEMENT = "HAS-ELEMENT"
    MAP_TYPE_MAP_TO = "MAP-TO"
    MAP_TYPES = [
        MAP_TYPE_SAME_AS,
        MAP_TYPE_PART_OF,
        MAP_TYPE_Q_AND_A,
        MAP_TYPE_NARROWER_THAN,
        MAP_TYPE_CONCEPT_SET,
        MAP_TYPE_SYSTEM,
        MAP_TYPE_BROADER_THAN,
        MAP_TYPE_HAS_ANSWER,
        MAP_TYPE_HAS_ELEMENT,
        MAP_TYPE_MAP_TO,
    ]
    DATA_TYPE_BOOLEAN = 'Boolean'
    DATA_TYPE_COMPLEX = "Complex"
    DATA_TYPE_STRUCTURED_NUMERIC = "Structured-Numeric"
    DATA_TYPE_RULE = "Rule"
    DATA_TYPE_DATETIME = "Datetime"
    DATA_TYPE_TIME = "Time"
    DATA_TYPE_DATE = "Date"
    DATA_TYPE_DOCUMENT = "Document"
    DATA_TYPE_CODED = "Coded"
    DATA_TYPE_STRING = "String"
    DATA_TYPE_TEXT = "Text"
    DATA_TYPE_NA = "N/A"
    DATA_TYPE_NUMERIC = "Numeric"
    DATA_TYPE_NONE = "None"
    DATA_TYPES =[
        DATA_TYPE_BOOLEAN,
        DATA_TYPE_CODED,
        DATA_TYPE_STRING,
        DATA_TYPE_TEXT,
        DATA_TYPE_NA,
        DATA_TYPE_NUMERIC,
        DATA_TYPE_NONE,
        DATA_TYPE_COMPLEX,
        DATA_TYPE_STRUCTURED_NUMERIC,
        DATA_TYPE_RULE,
        DATA_TYPE_DATETIME,
        DATA_TYPE_TIME,
        DATA_TYPE_DATE,
        DATA_TYPE_DOCUMENT
    ]
    DESCRIPTION_TYPE_DEFINITION = "Definition"
    DESCRIPTION_TYPE_NONE = "None"
    DESCRIPTION_TYPES = [
        DESCRIPTION_TYPE_DEFINITION,
        DESCRIPTION_TYPE_NONE
                         
    ]
    NAME_TYPE_INDEX_TERM = "Index-Term"
    NAME_TYPE_SHORT = "Short"
    NAME_TYPE_FULLY_SPECIFIED = "Fully-Specified"
    NAME_TYPE_NONE = "None"
    NAME_TYPES = [
        NAME_TYPE_INDEX_TERM,
        NAME_TYPE_SHORT,
        NAME_TYPE_FULLY_SPECIFIED,
        NAME_TYPE_NONE                   
    ]
OCLRessourceType= Literal[tuple(OclConstants.RESOURCE_TYPES)]


def get_data_type(tricc_type):
    if tricc_type.lower() in ('integer', 'decimal', 'add', 'count'):
        return OclConstants.DATA_TYPE_NUMERIC
    elif tricc_type.lower() in ('activity', 'page'):
        return OclConstants.DATA_TYPE_DOCUMENT
    elif tricc_type.lower() in ('select_one'):
        return OclConstants.DATA_TYPE_CODED
    elif tricc_type.lower() in ('calculate', 'diagnosis', 'proposed_diagnosis'):
        return OclConstants.DATA_TYPE_BOOLEAN
    found_type = [ t  for t in OclConstants.DATA_TYPES if t.lower() == tricc_type.lower()]
    if found_type:
        return found_type[0]
    return OclConstants.DATA_TYPE_NA
 
class OCLBaseModel(BaseModel):
    type:OCLRessourceType
    id:OCLId
    external_id:str = None
    public_access:Literal[tuple(OclConstants.ACCESS_TYPES)] = OclConstants.ACCESS_TYPE_VIEW
    extras:Dict[str,Union[str,Dict[str,str]]] = {}
    url: Union[AnyHttpUrl,Uri] = None
    # enriched data for get
class OclGet(BaseModel):
    created_on:str = None
    created_by:str = None
    updated_on:str = None
    updated_by:str = None
    
class OCLBaseModelBrowsable(OCLBaseModel):
    name:OCLName
    description:str = None
    website:AnyHttpUrl = None
    

class OCLDetailedName(BaseModel):
    name: str
    external_id:str = None
    locale:OCLLocale
    locale_preferred:Boolean = None
    name_type:Literal[tuple(OclConstants.NAME_TYPES)] = OclConstants.NAME_TYPE_SHORT

class OCLDetailedDescription(BaseModel):
    description:str
    external_id:str = None
    locale:OCLLocale
    locale_preferred:Boolean = None
    description_type:Literal[tuple(OclConstants.DESCRIPTION_TYPES)] = OclConstants.DESCRIPTION_TYPE_DEFINITION

class OCLConcept(OCLBaseModel):
    type:OCLRessourceType = OclConstants.RESOURCE_TYPE_CONCEPT
    uuid: str = None
    concept_class: str
    datatype:Literal[tuple(OclConstants.DATA_TYPES)] = OclConstants.DATA_TYPE_NONE
    names:List[OCLDetailedName]
    descriptions: List[OCLDetailedDescription] = []
    retired:Boolean = False
    # not for create
    versions: str = None # TODO version
    source:OCLId = None
    owner:OCLId = None
    owner_type:Literal[tuple(OclConstants.OWNER_TYPE_TO_STEM)] = None    
    owner_url:Union[AnyHttpUrl,Uri] = None
    versions_url:Union[AnyHttpUrl,Uri] = None
    source_url:Union[AnyHttpUrl,Uri] = None
    owner_url:Union[AnyHttpUrl,Uri] = None
    mappings_url:Union[AnyHttpUrl,Uri] = None
    
class OCLMapping(BaseModel):
    type:OCLRessourceType = OclConstants.RESOURCE_TYPE_MAPPING
    uuid: str = None
    retired:Boolean = False
    map_type: Literal[tuple(OclConstants.MAP_TYPES)]
    from_concept_url:Union[AnyHttpUrl,Uri]
    from_source_url:Uri = None
    from_concept_code:str = None
    from_concept_name:str = None
    to_concept_url:Union[AnyHttpUrl,Uri] = None
    to_source:str = None
    to_concept_code:str = None
    to_source_owner:OCLId = None
    to_source_owner_type:Literal[tuple(OclConstants.OWNER_TYPE_TO_STEM)] = None
    #for bulk
    source:OCLId = None
    owner:OCLId = None
    owner_type:Literal[tuple(OclConstants.OWNER_TYPE_TO_STEM.values())] = None

class OCLCollection(OCLBaseModelBrowsable):
    #TODO https://docs.openconceptlab.org/en/latest/oclapi/apireference/collections.html
    pass

class OCLUser(OCLBaseModelBrowsable):
    #TODO https://docs.openconceptlab.org/en/latest/oclapi/apireference/users.html
    pass 
    
class  OCLMappingInternal(OCLMapping):             
    to_concept_url:Union[AnyHttpUrl,Uri]
    # when there is not URL
    
class  OCLMappingExternal(OCLMapping):   
    to_source_url:Uri
    to_concept_code:str
    to_concept_name:str = None
        
class OCLOrganisation(OCLBaseModelBrowsable):
    type:OCLRessourceType = OclConstants.RESOURCE_TYPE_ORGANIZATION
    company:OCLName
    logo_url:AnyHttpUrl
    location:OCLName
    text:str
    
    

class OCLSource(OCLBaseModelBrowsable):
    type:OCLRessourceType = OclConstants.RESOURCE_TYPE_SOURCE
    short_code:OCLShortName
    full_name:OCLName
    source_type:Literal[tuple(OclConstants.SOURCE_TYPES)] = OclConstants.SOURCE_TYPE_DICTIONARY
    default_locale:OCLLocale = 'en'
    supported_locales:List[OCLLocale] = ['en']
    custom_validation_schema:str = 'None'
    # not for create
    owner:OCLId = None
    owner_type:Literal[tuple(OclConstants.OWNER_TYPE_TO_STEM)] = None
    owner_url:Union[AnyHttpUrl,Uri] = None
    #FHIR
    hierarchy_meaning:Literal[tuple(OclConstants.HIERARCHY_MEANINGS)] = None
    hierarchy_root_url:Union[AnyHttpUrl,Uri] = None
    meta:str = None
    canonical_url:Union[AnyHttpUrl,Uri] = None
    internal_reference_id:OCLId = None
    #collection_reference:Uri
    versions_url:Union[AnyHttpUrl,Uri] = None
    concepts_url:Union[AnyHttpUrl,Uri] = None
    mappings_url:Union[AnyHttpUrl,Uri] = None
    
    versions: str = None # TODO version
    active_concepts:int = 0
    active_mappings:int = 0
    
class OCLSourceVersion(OCLBaseModelBrowsable):
    released: Boolean = None
    previous_version :str
    parent_version :str