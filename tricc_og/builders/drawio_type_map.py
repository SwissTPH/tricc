from tricc_og.models.tricc import TriccNodeType

TYPE_MAP = {
    TriccNodeType.start: {
        "objects": ["UserObject", "object"],
        "attributes": [],
        "mandatory_attributes": [],
    },
    TriccNodeType.activity_start: {
        "objects": ["UserObject", "object"],
        "attributes": [],
        "mandatory_attributes": [],
    },
    TriccNodeType.note: {
        "objects": ["UserObject", "object"],
        "attributes": [],
        "mandatory_attributes": [],
    },
    TriccNodeType.hint: {
        "objects": ["UserObject", "object"],
        "attributes": [],
        "mandatory_attributes": [],
    },
    TriccNodeType.help: {
        "objects": ["UserObject", "object"],
        "attributes": [],
        "mandatory_attributes": [],
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
        ],
        "mandatory_attributes": [],
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
        ],
        "mandatory_attributes": [],
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
        ],
        "mandatory_attributes": [],
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
        ],
        "mandatory_attributes": [],
    },
    TriccNodeType.integer: {
        "objects": ["UserObject", "object"],
        "attributes": ["constraint", "save", "constraint_message", "required"],
        "mandatory_attributes": [],
    },
    TriccNodeType.text: {
        "objects": ["UserObject", "object"],
        "attributes": [],
        "mandatory_attributes": [],
    },
    TriccNodeType.date: {
        "objects": ["UserObject", "object"],
        "attributes": [],
        "mandatory_attributes": [],
    },
    TriccNodeType.add: {
        "objects": ["UserObject", "object"],
        "attributes": ["save", "expression"],
        "mandatory_attributes": [],
    },
    TriccNodeType.count: {
        "objects": ["UserObject", "object"],
        "attributes": ["save", "expression"],
        "mandatory_attributes": [],
    },
    TriccNodeType.rhombus: {
        "objects": ["UserObject", "object"],
        "attributes": ["save", "expression"],
        "mandatory_attributes": ["reference"],
    },
    TriccNodeType.wait: {
        "objects": ["UserObject", "object"],
        "attributes": ["save", "expression"],
        "mandatory_attributes": ["reference"],
    },
    TriccNodeType.exclusive: {
        "objects": ["UserObject", "object"],
        "attributes": [],
        "mandatory_attributes": [],
    },
    TriccNodeType.not_available: {
        "objects": ["UserObject", "object"],
        "attributes": [],
        "mandatory_attributes": [],
    },
    TriccNodeType.select_yesno: {
        "objects": ["UserObject", "object"],
        "attributes": [
            "required",
            "save",
            "filter",
            "constraint",
            "constraint_message",
        ],
        "mandatory_attributes": [],
    },
    TriccNodeType.link_out: {
        "objects": ["UserObject", "object"],
        "attributes": [],
        "mandatory_attributes": ["reference"],
    },
    TriccNodeType.link_in: {
        "objects": ["UserObject", "object"],
        "attributes": [],
        "mandatory_attributes": [],
    },
    TriccNodeType.goto: {
        "objects": ["UserObject", "object"],
        "attributes": ["instance"],
        "mandatory_attributes": ["link"],
    },
    TriccNodeType.end: {
        "objects": ["UserObject", "object"],
        "attributes": [],
        "mandatory_attributes": [],
    },
    TriccNodeType.activity_end: {
        "objects": ["UserObject", "object"],
        "attributes": [],
        "mandatory_attributes": [],
    },
    TriccNodeType.bridge: {
        "objects": ["UserObject", "object"],
        "attributes": [],
        "mandatory_attributes": [],
    },
}
