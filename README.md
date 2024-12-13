# design  rules tricc_oo

## Nodes

## Node Types and Properties

**Start Node**
This node type represents the beginning of a process. It requires a label and can have attributes like process, parent, and form_id.

**Activity Start Node**
Marking the start of an activity, this node type needs both a label and a name. It can have attributes such as parent and instance.

**Note Nodes**
This node type are used for providing  information. Note nodes require both a label and a name,.

**Selection Nodes**
There are three types of selection nodes:
- Select One: For single-choice selections
- Select Multiple: For multiple-choice selections
- Select Yes/No: For binary choices

All these nodes require a label, name, and list_name. They can have attributes like required, save, filter, constraint, and constraint_message.

**Numeric Input Nodes**
Decimal and Integer nodes are used for numeric input. They require a label and name, and can have attributes like min, max, constraint, save, constraint_message, and required. 

**Text and Date Nodes**
These nodes are for text input and date selection. Both require a label and name.

**Calculation Nodes**
Add, Count, and Calculate nodes are used for various calculations. They require a label and name, and can have save and expression attributes

**Flow Control Nodes**
Rhombus and Wait nodes are used for flow control. They require a reference, name, and label, and can have save and expression attributes. 

**Exclusive Node**
This node type doesn't have any mandatory attributes or specific attributes defined.

**Not Available Node**
Used to indicate unavailability, this node requires a label, name, and list_name.

**Link Nodes**
Link Out and Link In nodes are used for creating connections. Link Out requires a reference, label, and name, while Link In only needs a label and name. 

**Go To Node**
This node is used for navigation. It requires a link, label, and name, and can have an instance attribute. 

**End Nodes**
End and Activity End nodes mark the conclusion of processes or activities.

**Bridge Node**
This node can have a label attribute but doesn't have any mandatory attributes. 

**Diagnosis Node**
Used for diagnostic purposes, this node requires a name and label

### Enrichment

Node can be enriched with message and media, simply add the media on the draw.io andlink them with an edge

**Image Node**
Used to add image to a question

**Hint Message Node**
Used to add an hint message to a question, need a label

**Help Message Node**
Used to add an help message to a question, need a label

## Attributes

**expression**
replace the calcualte deducted by inputs

**default**
not supported yet

**save**
will create a calculate with the same name
- obs: observation: save the option as a calcualte obs_[name of the option]
  - can be written obs.[othername].[snomedCode]
- diag: diagnostic/classification save the option as a calcualte diag_[name of the option]
- flag: calculate save the option as a calcualte is_[name of the option]


## Edges

The edge are in general labeless unless for :
    - after a select multiple: can setup quick rhombus for the number of choice selected, an opperator is required (<>=) in the edge label
    - after a yes/no quesiton:  'Yes', 'No', 'Follow' (translation can be added in the code )
    - before a calculate to put weight: integer only


# notes

## advanced interpretation of the edges:

Activity instances: if there is more that 1 instance of a single actity then the 1+ activity will be displayed only if the previous one were not, to do that the GoTO node are replaced by a path and a rombhus, the path got to the activitvy and rhombus and the next node (if any) are attached to the rhombus that is use to wait that the activity

the node following an 1+ activity will be display after the activy OR instead of the activity

Select multiple: if followed by a calculate (rhombus included) the calculate will be equal to the number of selected option BUT opt_none
if not a calculate then relevance will be used unless it is "required" then condition will be at least 1 selection

the Rhombus act as an AND between its imputs and its reference BUT it is an OR beween the inputs
(input1 OR input2 OR input3) AND reference

## start nodes

### Main start

the flow required at least 1 main start node, but in case of cdss output strategy , several could be used given that they have a 'process' atrribute

here is the list of the CPG process, this will be the execution oder too:
- **registration**,
- **triage**,
- **emergency-care**,
- **local-urgent-care**,
- **actue-tertiary-care**,
- **history-and-physical**,
- **diagnostic-testing**,
- **determine-diagnosis**,
- **provide-counseling**,
- **dispense-medications**,
- **monitor-and-follow-up-of-patient**,
- **alerts-reminders-education**,
- **discharge-referral-of-patient**,
- **charge-for-service**,
- **record-and-report** 
	
	
# READ Xressource
https://jgraph.github.io/drawio-tools/tools/convert.html

option can have only incoming edge from images to be placed as option$


# Note

## generation of the expressions 

### add calcualte:

 - Non or No in an egde will generate a negate node
 - save adds a calcualte
 - a rhombus will generate a calcualte using the reference (can you the label as a test, either with comparaisin or option selected with [option label])

### for calculate 
    
Then we calculate based on the previous nodes: [get_prev_node_expression]
    - if a "fake" calculate (Rhombus, exclusion) then get the underlying expression (should not depend of Calcualte = true) [get_calculation_terms]
    - if a Select, manage it as a calculate too (should not depend of Calcualte = true) [get_calculation_terms]
    - else get the expression via  [get_calculation_terms] [get_prev_node_expression , calculate = False] -> get_node_expression for the prev node
