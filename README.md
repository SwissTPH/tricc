# TRICC

# OR

if 2+ arrows arrive in the same box then the logic will be consider as an OR BUT is the box is a diamand

# AND

Same as OR but for the diamant (odk_type : rhombus)

Questions:
- Can I assign the same calculate multiple time
- can I link a calculate to another calculate
- 


# format params
## odk_type : define the XFORM question type
### base type
- select_multiple
- select_one
- note

### tricc type
- rhombus: use an existing value/calcualte
- loose_link: add a constraint: start_before the linked activity
- hard_link: start the linked activity within the target activity
- main_start: main start of the algo
- activity_start: start of an activity (link in)
- count: count the number of valid input

## save: define is the value will be used 
- obs: observation: save the option as a calcualte obs_[name of the option]
  - can be written obs.[othername](snomeCode)
- diag: diagnostic/classification save the option as a calcualte diag_[name of the option]
- flag: calculate save the option as a calcualte is_[name of the option]

READ Xressource
https://jgraph.github.io/drawio-tools/tools/convert.html


option can have only incoming edge from images to be placed as option