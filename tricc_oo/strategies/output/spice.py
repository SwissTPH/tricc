import json
import os
import logging
from collections import OrderedDict
from pydantic import BaseModel
from tricc_oo.models import (
    TriccOperation,
    TriccOperator,
    TriccNodeSelect,
    TriccNodeSelectOne,
    TriccNodeAcceptDiagnostic,
    TriccNodeSelectYesNo,
    TriccNodeSelectMultiple,
    TriccNodeText,
    TriccNodeActivity,
    TriccNodeInteger,
    OrderedSet,
    TriccNodeNote,
    TriccNodeDiagnosis,
    TriccNodeSelectOption
)

from tricc_oo.converters.datadictionnary import lookup_codesystems_code

from tricc_oo.visitors.tricc import (
    check_stashed_loop,
    walktrhough_tricc_node_processed_stached,
    is_ready_to_process,
    process_reference,
    get_node_expressions
)

from tricc_oo.strategies.output.base_output_strategy import BaseOutPutStrategy

logger = logging.getLogger("default")

   
    

    
class spiceCondition():
    eq: str = None
    targetId: str = None
    visibility: str = 'visible' # other option gone
    
    def __init__(self, eq=None, targetId=None, visibility='visible'):
        self.eq = eq
        self.targetId = targetId
        self.visibility = visibility

    
    def __repr__(self):
        self.__str__()
    def to_dict(self):
        # Create a dictionary with only the required attributes
        return {
            "eq": self.eq,
            "targetId": self.targetId,
            "visibility": self.visibility
        }


class spiceOption():
    id: str = None
    name: str = None
    def __init__(self, id=None, name=None):
        self.id = id
        self.name = name

    
    def __repr__(self):
        self.__str__()
        
    def to_dict(self):
        # Create a dictionary with only the required attributes
        return {
            "id": self.id,
            "name": self.name,
        }
        
class SpiceQuestion():
    condition: list = []
    errorMessage: str = None
    family: str = None
    titleSummary: str = None
    fieldName: str = None
    id: str = None
    isEnabled: bool = None
    isEnabled: bool = True
    isMandatory: bool = True
    isNeededDefault: bool = False
    isBooleanAnswer: bool = False
    isSummary: str = None
    optionsList: list = []
    optionType: str = 'boolean'
    orderId: str = None
    readOnly: bool = True
    title: str = None
    viewType: str = None
    isInfo: str = 'gone'
    visibility: str = 'visible'
    noOfDays: int = None
    
    def to_dict(self):
        """
        Returns a dictionary representation of the object,
        including only attributes that are not None or empty lists.
        """
        return {
            key: value for key, value in self.__dict__.items()
            if value is not None and value != []
        }
        

def get_node_options(node):
    options =  []
    if isinstance(node, TriccNodeSelect):
        for k,o in node.options.items():
            options.append(
                spiceOption(
                    id=o.name,
                    name=o.label
                ).to_dict()
            )
        return options
                
def get_node_conditions(node):
    conditions =  []
    if isinstance(node, TriccNodeSelect):
        for k,o in node.options.items():
            for n in o.next_nodes:
                conditions.append(
                    spiceCondition(
                        eq=o.name,
                        targetId=n.name,
                        visibility='visible' # other option gone                      
                    ).to_dict()
                )
        return conditions
        
def get_option_type(node):
    if isinstance(node, (TriccNodeSelectYesNo, TriccNodeAcceptDiagnostic)):
        return 'boolean'
    elif isinstance(node, TriccNodeSelect):
        #FIXME no other value than boolean found
        return 'string'

def get_node_view_type(node, concept):
    if isinstance(node, TriccNodeSelectOne):
        return 'SingleSelectionView'
    elif isinstance(node, TriccNodeSelectMultiple):
        #FIXME
        return 'Spinner'
    elif isinstance(node, TriccNodeText):
        return 'EditText'
    elif is_no_of_day(node,concept):
        return 'NoOfDaysView'
    elif isinstance(node, TriccNodeNote):
        #FIXME
        return 'InformationLabel'
    elif isinstance(node, TriccNodeDiagnosis):
        #FIXME
        return 'InformationLabel'
   

    
    
def is_no_of_day(node, concept):
    return (
        isinstance(node, TriccNodeInteger) 
        and concept
        and any(
            [
                True for p in concept.property 
                if p.valueString == 'nbDays' and p.code == 'archetype'
                ]
            )
    )
    
def to_spice_question(node, codesystems):
    concept = lookup_codesystems_code(codesystems, node.name)
    view_type = get_node_view_type(node,concept)
    if view_type:
        
        q = SpiceQuestion()
        q.condition=get_node_conditions(node)
        q.errorMessage=getattr(node, 'constraint_message', None)
        q.family= (node.group or node.activity).name
        q.titleSummary= (node.group or node.activity).label
        q.fieldName= node.label
        q.isEnabled= True
        q.isMandatory= True
        q.isNeededDefault= True
        q.isBooleanAnswer= isinstance(node, TriccNodeSelectYesNo)
        q.isSummary=any([True for p in concept.property if p.valueBoolean == True and p.code == 'isSummary']) if concept and concept.property else None
        q.optionsList= get_node_options(node)
        q.optionType= get_option_type(node)
        q.orderId= node.path_len
        q.readOnly= isinstance(node, TriccNodeNote)
        q.title= node.label
        q.isInfo= 'gone'
        q.visibility = 'gone' if node.prev_nodes else 'visible'
        q.viewType = view_type
        q.noOfDays = node.default if is_no_of_day(node, concept) else None
        return q
    elif not isinstance(node, TriccNodeSelectOption):
        logger.warning(f"unsuported question type {node.get_name()} ")

    

class SpiceStrategy(BaseOutPutStrategy):
    form_layout = []
    groups = []
    def __init__(self, project, output_path):
        super().__init__(project, output_path)
        self.form_layout = []
        self.groups = []


    def process_base(self, start_pages, **kwargs):
        # for each node, check if condition is required issubclass(TriccNodeDisplayModel)
        # process name
        pass
        
    def process_relevance(self, start_pages, **kwargs):
        
        pass
    
    def process_calculate(self, start_pages, **kwargs):
        # call the strategy specific code
        pass
        

    def do_clean(self):
        self.form_layout = []
        self.groups = []


    def get_kwargs(self):
        return {
            "form_layout": self.form_layout,
            "group": self.groups,

        }

    def generate_export(self, node, processed_nodes, calculates, **kwargs):
        # Export logic to JSON format
        if is_ready_to_process(node,processed_nodes, strict=True) and process_reference(node, processed_nodes, calculates, replace_reference=False, codesystems= kwargs.get('codesystems', None)) :
            if node not in processed_nodes :
                self.start_group(cur_group=node.group or node.activity)
                if not isinstance(node, TriccNodeActivity):
                    q = to_spice_question(node, self.project.code_systems)
                    if q:
                        self.form_layout.append(
                            q.to_dict()
                        )
                return True

    def export(self, start_pages, version):
        # Save the JSON output to a file
        file_name = f"{start_pages['main'].root.form_id}.json"
        output_path = os.path.join(self.output_path, file_name)
        
        
        
        with open(output_path, 'w') as json_file:
            json.dump({"formLayout": self.form_layout}, json_file, indent=4)
        
        logger.info(f"JSON form exported to {output_path}")

    def process_export(self, start_pages, **kwargs):
        # Process nodes and export as JSON
        self.activity_export(start_pages["main"], **kwargs)

    def start_group(self, cur_group):
        if cur_group.get_name() not in self.groups:
            self.groups.append(cur_group.get_name())
            self.form_layout.append(
                 {
                    "familyOrder": len(self.groups),
                    "id": cur_group.name,
                    "title": cur_group.label,
                    "viewType": "CardView"
                }
            )


    def activity_export(self, activity, processed_nodes=OrderedSet(), **kwargs):
        stashed_nodes = OrderedSet()
        calculates = []
        cur_group = activity

        path_len = 0
        # keep the vesrions on the group id, max version
        
        self.start_group(cur_group)
        walktrhough_tricc_node_processed_stached(
            activity.root,
            self.generate_export,
            processed_nodes,
            stashed_nodes,
            path_len,
            cur_group=activity.root.group,
            calculates = calculates,
            **self.get_kwargs()
        )
        ## MANAGE STASHED NODES
        prev_stashed_nodes = stashed_nodes.copy()
        loop_count = 0
        len_prev_processed_nodes = 0
        while len(stashed_nodes) > 0:
            loop_count = check_stashed_loop(
                stashed_nodes,
                prev_stashed_nodes,
                processed_nodes,
                len_prev_processed_nodes,
                loop_count,
            )
            prev_stashed_nodes = stashed_nodes.copy()
            len_prev_processed_nodes = len(processed_nodes)
            if len(stashed_nodes) > 0:
                s_node = stashed_nodes.pop()
                # while len(stashed_nodes)>0 and isinstance(s_node,TriccGroup):
                #    s_node = stashed_nodes.pop()
                if len(s_node.prev_nodes) > 0:
                    path_len = (
                        sorted(
                            s_node.prev_nodes,
                            key=lambda p_node: p_node.path_len,
                            reverse=True,
                        )[0].path_len
                        + 1
                    )
                # arrange empty group
                walktrhough_tricc_node_processed_stached(
                    s_node,
                    self.generate_export,
                    processed_nodes,
                    stashed_nodes,
                    path_len,
                    groups=groups,
                    cur_group=s_node.group,
                    calculates = calculates,
                    **self.get_kwargs()
                )
       
        return processed_nodes

        # Handle stashed nodes (if needed)
    def tricc_operation_equal(self, ref_expressions):
        return {
          "eq": str(ref_expressions[1]),
          "targetId": str(ref_expressions[0]),
          "visibility": "visible"
        }

    def tricc_operation_in(self, ref_expressions):
        return {
          "eq": str(ref_expressions[0]),
          "targetId": str(ref_expressions[1]),
          "visibility": "visible"
        }
    
    def tricc_operation_in(self, ref_expressions):
        return ref_expressions[0].replace('visible', 'gone')