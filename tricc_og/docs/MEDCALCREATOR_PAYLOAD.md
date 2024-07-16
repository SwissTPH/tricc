# how to read Medal Creator payload

diagnose
 - "id": reference of the diagnose
 - "label": multilingual labels
 - "complaint_category": diagnose triggered by ,
 - "cut_off_start": age in day offset,
 - "cut_off_end": age in day limit,
 - "instances": edges between nodes within diagnoses, (including Q defined for df )
 - "final_diagnoses": "instance" specific to df , 

node
 - "id": 7339,
 - "type": "Question",
 - "label": multilingual labels
 - "description": multilingual description
 - "is_mandatory": Self explainatory boolean  #TODO
 - "is_neonat": Self explainatory boolean, looks redundant with cut offs
 - "is_pre_fill": Self explainatory boolean #TODO from patient data
 - "vital_signs": [] UNSUPORTED list
 - "emergency_status": UNSUPORTED string null, 'standard', 'referal', 'emergency'
 - "category": type of question
 - "is_identifiable": UNSUPORTED bool : for search ? 
 - "is_danger_sign": UNSUPORTED bool
 - "unavailable": add the "unavailaible box" #TODO
 - "unavailable_label": multilang labels for unavailaible,
 - "display_format": "Formula" / "Input"/"RadioButton" / "DropDownList",
 - "qs": [], parent QS
 - "dd": [], parent DD
 - "df": [], condition by df (antagonist final_diagnosis_id) TODO if the condition in dianoses.instance are sufficient
 - "conditioned_by_cc": [], works only for cc
 - "referenced_in": [],UNSUPORTED list TDOD used in calculate ?
 - "answers": list of answer
 - "medias": [] list of media to use #TODO
 - system: full order section

 background_calculation (in additon to node)

 - "formula": List of the nodes on which the calculation is based
 - "category": "background_calculation"
 - "estimable": UNSUPORTED bool
 - "value_format": "Float",
 - "display_format": "Formula",

 answers:
    "id": reference
    "reference":  local reference / display order
    "label": 

 anwers (calculate, in addition to answer): 
    "value": "7,29", comma separated value used in calulation (only for background_calculate)
    "operator": "between"

QuestionSequence (in additon to node)
 - "conditions":
 - "instance" : edges if the inside questions

final diagnistic
 - "conditions": # TRigger equi instance.condition
 - "diagnosis_id": 8066, #TODO
 - "id": 40297,
 - "reference": 543, #TODO  local reference / display order
 - "label": 
 - "description":
 - "level_of_urgency": 5,
 - "medias": [],
 - "type": "FinalDiagnosis",
 - "drugs": edges for the drugs inside the FD,
 - "managements": management
 - "excluding_final_diagnoses": [40219   ],
 - "cc": 7803

 
 Management:
 - "conditions": [],
 - "id": 8217,
 - "is_pre_referral": false,
 - "description": 
        
instance
 - "conditions": edge source : question/answer required , empty for root
 - "id": ,
 - "children":  to nodes (QS id or in condition of another question)
 - "final_diagnosis_conditions": null --> question conditionned by df
