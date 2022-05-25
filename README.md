# TRICC

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
    container_hint_media:
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