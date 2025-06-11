from strenum import StrEnum
from tricc_oo.models.base import *
from tricc_oo.models.calculate import *


TYPE_MAP = {
    TriccNodeType.start: {
        "objects": ["UserObject", "object"],
        "attributes": ['process', 'parent', 'form_id','relevance',"priority"],
        "mandatory_attributes": ["label"],
        "model": TriccNodeMainStart
    },
    TriccNodeType.activity_start: {
        "objects": ["UserObject", "object"],
        "attributes": ['parent', 'parent', 'instance', 'relevance',"priority"],
        "mandatory_attributes": ["label", "name"],
        "model": TriccNodeActivityStart
    },
    TriccNodeType.note: {
        "objects": ["UserObject", "object"],
        "attributes": ['relevance',"priority"],
        "mandatory_attributes": ["label", "name"],
        "model": TriccNodeNote
    },
    TriccNodeType.hint: {
        "objects": ["UserObject", "object"],
        "attributes": [],
        "mandatory_attributes": ["label"],
        "model": None
    },
    TriccNodeType.help: {
        "objects": ["UserObject", "object"],
        "attributes": [],
        "mandatory_attributes": ["label"],
        "model": None
    },
    TriccNodeType.select_one: {
        "has_options": True,
        "objects": ["UserObject", "object"],
        "attributes": [
            "required",
            "save",
            "filter",
            "constraint",
            "constraint_message",
            "relevance",
            "priority"

        ],
        "mandatory_attributes": ["label", "name", "list_name"],
        "model": TriccNodeSelectOne
    },
    TriccNodeType.select_multiple: {
        "has_options": True,
        "objects": ["UserObject", "object"],
        "attributes": [
            "required",
            "save",
            "filter",
            "constraint",
            "constraint_message",
            "relevance",
            "priority"
        ],
        "mandatory_attributes": ["label", "name", "list_name"],
        "model": TriccNodeSelectMultiple
    },
    TriccNodeType.decimal: {
        "objects": ["UserObject", "object"],
        "attributes": [
            "min",
            "max",
            "constraint",
            "save",
            "constraint_message",
            "required",
            "relevance",
            "priority"
        ],
        "mandatory_attributes": ["label", "name"],
        "model": TriccNodeDecimal
    },
    TriccNodeType.integer: {
        "objects": ["UserObject", "object"],
        "attributes": [
            "min",
            "max",
            "constraint",
            "save",
            "constraint_message",
            "required",
            "relevance",
            "priority"
            
        ],
        "mandatory_attributes": ["label", "name"],
        "model": TriccNodeInteger
    },

    TriccNodeType.text: {
        "objects": ["UserObject", "object"],
        "attributes": ["save", "relevance","priority"],
        "mandatory_attributes": ["label", 'name'],
        "model": TriccNodeText
    },
    TriccNodeType.date: {
        "objects": ["UserObject", "object"],
        "attributes": ["save", "relevance","priority"],
        "mandatory_attributes": ["label", "name"],
        "model": TriccNodeDate
    },
    TriccNodeType.add: {
        "objects": ["UserObject", "object"],
        "attributes": ["save", "expression"],
        "mandatory_attributes": ['label', "name"],
        "model": TriccNodeAdd
    },
    TriccNodeType.count: {
        "objects": ["UserObject", "object"],
        "attributes": ["save", "expression"],
        "mandatory_attributes": ['label', "name"],
        "model": TriccNodeCount
    },
    TriccNodeType.calculate: {
        "objects": ["UserObject", "object"],
        "attributes": ["save", "reference"],
        "mandatory_attributes": [ "name", 'label'],
        "model": TriccNodeCalculate
    },
    TriccNodeType.rhombus: {
        "objects": ["UserObject", "object"],
        "attributes": ["save", "expression", 'label','priority'],
        "mandatory_attributes": ["reference"],
        "model": TriccNodeRhombus
    },
    TriccNodeType.wait: {
        "objects": ["UserObject", "object"],
        "attributes": ["save", "expression"],
        "mandatory_attributes": ["reference", "name", 'label'],
        "model": TriccNodeWait
    },
    TriccNodeType.exclusive: {
        "objects": ["UserObject", "object"],
        "attributes": [],
        "mandatory_attributes": [],
        "model": TriccNodeExclusive
    },
    TriccNodeType.not_available: {
        "objects": ["UserObject", "object"],
        "attributes": [],
        "mandatory_attributes": ["label", "name", "list_name"],
        "model": TriccNodeSelectNotAvailable
    },
    TriccNodeType.select_yesno: {
        "objects": ["UserObject", "object"],
        "attributes": [
            "required",
            "save",
            "filter",
            "constraint",
            "constraint_message",
            "relevance","priority"
        ],
        "mandatory_attributes": ["label", "name", "list_name"],
        "model": TriccNodeSelectYesNo
    },
    TriccNodeType.link_out: {
        "objects": ["UserObject", "object"],
        "attributes": [],
        "mandatory_attributes": ["reference", "label", "name"],
        "model": TriccNodeNote
    },
    TriccNodeType.link_in: {
        "objects": ["UserObject", "object"],
        "attributes": [],
        "mandatory_attributes": ["label", "name"],
        "model": TriccNodeLinkIn
    },
    TriccNodeType.goto: {
        "objects": ["UserObject", "object"],
        "attributes": ["instance","priority"],
        "mandatory_attributes": ["link", "label", "name"],
        "model": TriccNodeGoTo
    },
    TriccNodeType.end: {
        "objects": ["UserObject", "object"],
        "attributes": ['process', 'name', 'label', 'hint'],
        "mandatory_attributes": ['label'],
        "model": TriccNodeEnd
    },
    TriccNodeType.activity_end: {
        "objects": ["UserObject", "object"],
        "attributes": [],
        "mandatory_attributes": [],
        "model": TriccNodeActivityEnd
    },
    TriccNodeType.bridge: {
        "objects": ["UserObject", "object"],
        "attributes": ["label","priority"],
        "mandatory_attributes": [],
        "model": TriccNodeBridge
    },
    TriccNodeType.diagnosis: {
        "objects": ["UserObject", "object"],
        "attributes": ["save", "reference", "priority"],
        "mandatory_attributes": [ "name", 'label'],
        "model": TriccNodeDiagnosis
    },
    TriccNodeType.proposed_diagnosis: {
        "objects": ["UserObject", "object"],
        "attributes": ["save", "reference", "severity", "priority"],
        "mandatory_attributes": [ "name", 'label'],
        "model": TriccNodeProposedDiagnosis
    },
    TriccNodeType.input: {
        "objects": ["UserObject", "object"],
        "attributes": ["save", "reference","datatype"],
        "mandatory_attributes": [ "name", 'label'],
        "model": TriccNodeInput
    },
        # TriccNodeType.number: {
    #     "objects": ["UserObject", "object"],
    #     "attributes": ["constraint", "save", "constraint_message", "required"],
    #     "mandatory_attributes": [],
    #     "model": TriccNodeNumber
    # },
}
