from pydantic import BaseModel, Enum, List, Optionnal, constr, Union

Expression= constr(regex="^[^/\]$")

class TriccNodeType(str, Enum):
    note='note'
    calculate='calculate'
    select_multiple='select_multiple'
    select_one='select_one'
    select_option='select_options'
    decimal='decimal'
    interger='interger'

class TriccExtendedNodeType(str, Enum):
    romhbus='romhbus' # fetch data
    loose_link='loose_link' #add a constraint: start_before the linked activity
    hard_link='hard_link'#: start the linked activity within the target activity
    main_start='main_start'#: main start of the algo
    activity_start='activity_start'#: start of an activity (link in)
    count='count'#: count the number of valid input

class TriccNodeModel(BaseModel):
    id:Optionnal[str]
    name: str
    odk_type: Union[TriccNodeType,TriccExtendedNodeType]
    # to use the enum value of the TriccNodeType
    class Config:  
        use_enum_values = True  # <--
    
class TriccNodeInputModel(TriccNodeModel):
    required=Optionnal[bool]
    constraint_message:Optionnal[str]
    constraint:Optionnal[Expression]
    
        
class calculate(TriccNodeModel):
    # TODO check if this is possible
    odk_type = TriccNodeType.calculate
    input: List[TriccNodeModel] = []
    save: Optionnal[str] # contribute to another calculate
    expression : Optionnal[Expression] # will be generated based on the input

class mainStart(TriccNodeModel):
    # TODO check if this is possible
    odk_type = TriccNodeType.main_start
    
class activityStart(TriccNodeModel):
    # TODO check if this is possible
    odk_type = TriccNodeType.activity_start
    
class hardLink(TriccNodeModel):
    # TODO check if this is possible
    odk_type = TriccNodeType.hard_link
    traget: activityStart
    
    
class looseLink(TriccNodeModel):
    # TODO check if this is possible
    odk_type = TriccNodeType.loose_link
    traget: activityStart
    

class selectOption(TriccNodeModel):
    # TODO check if this is possible
    odk_type = TriccNodeType.select_option
    

class select(TriccNodeInputModel):
    filter: Optionnal[str]
    options = List[selectOption]

class selectOne(select):
    odk_type = TriccNodeType.select_one

class selectYesNo(select):
    options:List['Yes', 'No']

class selectMultiple(select):
    odk_type = TriccNodeType.select_multiple

class decimal(TriccNodeInputModel):
    # TODO check if this is possible
    odk_type = TriccNodeType.decimal
    min=Optionnal[float]
    max=Optionnal[float]

class integer(TriccNodeInputModel):
    # TODO check if this is possible
    odk_type = TriccNodeType.interger
    min=Optionnal[int]
    max=Optionnal[int]