# TRICC
## Shape

    odk_type:

### Rhombus

    odk_type:

### calculate

    odk_type: calculate
### Negate/Exclusive

    odk_type:not

### Select Multiple

    odk_type:select_multiple

#### options

    odk_type:select_option

### Select one

    odk_type:select_one


#### Select YesNo

Not yet supported
#### options

    odk_type:select_option
### Text

    odk_type:text

### Note

    odk_type:note

### Decimal

    odk_type:decimal

### Enrichment

node that target another node to enrich it

#### Image

#### Hint

    odk_type:hint-message

#### Help

Commcare only, not yet supported

    odk_type:help-message

#### Not available

Diplay a checkbox to indicate that the data cannot be capture

    odk_type:not_available


### Links

Node that are made to link page of jump witnin a page

#### Start

#### Activity Start

#### activity end

#### End

#### Page/Container


## properties

### odk_type

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

advanced interpretation of the edges:

Activity instances: if there is more that 1 instance of a single actity then the 1+ activity will be displayed only if the previous one were not

the node folowing an 1+ activity will be display after the activy OR instead of the activity

Select multiple: if followed by a calculate (rhombus included) the calculate will be equal to the number of selected option BUT opt_none
if not a calculate then relevance will be used unless it is "required" then condition will be at least 1 selection

the Rhombus act as an AND between its imputs and its reference BUT it is an OR beween the inputs
(input1 OR input2 OR input3) AND reference



# READ Xressource
https://jgraph.github.io/drawio-tools/tools/convert.html


option can have only incoming edge from images to be placed as option