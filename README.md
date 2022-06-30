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

# READ Xressource
https://jgraph.github.io/drawio-tools/tools/convert.html


option can have only incoming edge from images to be placed as option