# TRICC

## Edges

    the edge are in general labeless unless for :
    - after a select multiple: can setup quick rhombus for the number of choice selected, an opperator is required (<>=)
    - after a yes/no quesiton:  'Yes', 'No', 'Follow' (translation can be added in the code )
    - before a calculate to put weight: integer only

## Shape

    tricc_type:

### Rhombus

    tricc_type:

### calculate

    tricc_type: calculate
### Negate/Exclusive

    tricc_type:not

### Select Multiple

    tricc_type:select_multiple

#### options

    tricc_type:select_option

### Select one

    tricc_type:select_one


#### Select YesNo

Not yet supported
#### options

    tricc_type:select_option
### Text

    tricc_type:text

### Note

    tricc_type:note

### Decimal

    tricc_type:decimal

### Enrichment

node that target another node to enrich it

#### Image

#### Hint

    tricc_type:hint-message

#### Help

Commcare only, not yet supported

    tricc_type:help-message

#### Not available

Diplay a checkbox to indicate that the data cannot be capture

    tricc_type:not_available


### Links

Node that are made to link page of jump witnin a page

#### Start

#### Activity Start

#### activity end

#### End

#### Page/Container


## properties

### tricc_type

    rhombus: fetch data
    goto: start the linked activity within the target activity
    start: main start of the algo
    activity_start: start of an activity (link in)
    link_in
    link_out
    count: count the number of valid input
    add: add counts
    (DEPRECATED)container_hint_media:
    activity:
    #select_yesno:
    select_option:
    hint:
    help:
    exclusive:
    end:
    activity_end:
    edge:
    page:
    note:
    calculate:
    select_multiple:
    select_one:
    decimal:
    integer:
    text:

### expression
replace the calcualte deducted by inputs
### expression_inputs
adds a calcualte to the one deducted by inputs

### default
not supported yet

### save
will create a calculate with the same name
- obs: observation: save the option as a calcualte obs_[name of the option]
  - can be written obs.[othername].[snomedCode]
- diag: diagnostic/classification save the option as a calcualte diag_[name of the option]
- flag: calculate save the option as a calcualte is_[name of the option]



### name
Mandatory

### label
Not a real property to add, it is simply the text display in the boxes


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

        - 'registration',
        - 'triage',
        - 'emergency-care',
        - 'local-urgent-care',
        - 'actue-tertiary-care',
        - 'history-and-physical',
        - 'diagnostic-testing',
        - 'determine-diagnosis',
        - 'provide-counseling',
        - 'dispense-medications',
        - 'monitor-and-follow-up-of-patient',
        - 'alerts-reminders-education',
        - 'discharge-referral-of-patient',
        - 'charge-for-service',
        - 'record-and-report' 


# READ Xressource
https://jgraph.github.io/drawio-tools/tools/convert.html


option can have only incoming edge from images to be placed as option$


# Note

## generation of the expressions [get_node_expressions]

### add calcualte:

 - Non or No will generate a negate node
 - save adds a calcualte
 - a rhombus will generate a calcualte in reference unless is is already the case (no left expression too)

### if the node is a calculate [get_node_expression, calculate = true]

    
    then we calculate based on the previous nodes: [get_prev_node_expression]
        - if a "fake" calculate (Rhombus, exclusion) then get the underlying expression (should not depend of Calcualte = true) [get_calculation_terms]
        - if a Select, manage it as a calculate too (should not depend of Calcualte = true) [get_calculation_terms]
        - else get the expression via  [get_calculation_terms] [get_prev_node_expression , calculate = False] -> get_node_expression for the prev node

### if the node is NOT a calculate [get_node_expression, calculate = false]

 
