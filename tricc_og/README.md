# TRICC-ON : Object networkx


This version of Tricc is made to merge the features of the tricc-oo and the networkx library (use in legacy triccs) while using BPMN principles (https://www.youtube.com/playlist?list=PLrAWWpbaj-7JlEV3_BfBLNYdYKrpqoC68)

The definitions will be slitted in 2 groups: the abstracted block definitions and the implementable definition (block and patterns).


## Project

Set of abstract Activity and authored Activity that will make an CDSS target to a specific use case. 


Project could be composed only of abstracted elements (Guideline project)

The generation of the L3 can only be done on a project level

Project need to have at least on  Activity (abstracted or not) that implement a CPG common process starts (main trigger)

* Project context parameters will be used to select the Task and Activity that will implement Abstract Activity and Abstract Task; it can also be used to select a specific path of exclusive gateway; In order to select the relevant implementation, the implementation activity will need to have a trigger based on project context parameters. Project context parameters could be hard coded and use a "formula"

* several L3 generation might be possible inside a single project giving that each will respect the constraints enunciated above

## Actor ? 

## GateWay

## Event

- start (catching a trigger)
- end (throw a trigger)
- intermediate: catch/throw trigger

## Data object 

## Edge

Source
Source_named_output (optional)
Target
Target_named_output (optional)
context (Activity that defines it )
Value (weight,label)
type of edges: Trigger or calculate

## task with several outputs:

task may have several outputs (or options) they will take the for a attributes output_options[x]

### Abstract Elements 

Abstract element are guideline element that must not details the implementation of the task and activity, they are limited to sequencing 


### Abstract Activity

aka: Abstract compounded Activity

Abstract Activity will have to defined:

- Inputs:
    - Optional data element, including the condition the data must respect (search parameters)
    - Mandatory data element (pre-requisite, data must be found to start this Activity), including the condition the data must respect (search parameters)
- Output:
    - Optional output data elements, including data validation rules
    - Mandatory output data elements
- Optionally a List of included Abstract Activity 
- Optionally a List of included Abstract Task
- Optionally a graph that attach the abstract Activity/node together
- Optionally list of named input

In order to generate an L3 it needs to be implemented by a "Authored Activity"

### Abstract Task

aka: call activity

In order to generate an L3 it needs to be implemented by a "Authored Activity" or a "Authored Task"


## Authored elements

Implementation elements have a System/Code|version referencing an Abstract Element System/Code|version and possibly their own System/Code

Applicability:  Condition of that need to be respected for this element to be a suitable implementation of the Abstract element (Project/ Context parameters)

Documentation List<{title, notes, List<references>}> will be present

### Authored Activity

Aka: compounded Activity

Activity will have to defined:

- Inputs:
    - Optional data element, 
    - Mandatory data element, inherited from abstract
- Output:
    - Optional output data elements, including data validation rules
    - Mandatory output data elements, inherited from abstract    


TBD: should input provide the default task/activity to use to collect them if missing ? 



### dataObject

use to save a variable from a task (incoming flow : output) or to retrieve a variable   (outgoing flow : inputs)


### Authored Task

aka: Node

Type: system/code|version: use to convert to L3 if there is no converter based on the task system/code|version

## Implementation elements

Purely computed level that depends on the strategy, this should generate a representation compatible with the desired L3    

# Logic

the logic formula need to be generic enough so they could be transformed later into different language

The grammar should be close to HL7 CQL or FEEL with the limitation that only identifier could be used: no resource type, no attributes

library."Identifier label" or library.`code`

the Activity or project may have their own library, therefore if an identifier is specified without it library it should exist in the "current" library


# L3 generation

L3 generation will be based on 2 paradigms:

- Main strategy that should cover the gateway conversion and transaction (the Decision logic conversion)
- Converters that should be capable of converting an activity into an L3 resource or snippet

L3 converted content could be various, questionnaire, backend script, AI, etc 


# L2 to L3 workflow




# Misc

## variable Nomenclature

to enable an easy editing some rules are required, proposed reserved name, the strategy must implement resolver for them

- patient object to access basic patient information (.age_in_days, .age_in_months, .age_in_years, .sex )
- obs -> prefix for Observation during the encounter
- historicObs[nb_days] -> prefix for history of Observation
- cond -> prefix for Condition during the encounter
- historicCond[nb_days] -> prefix for for history of Condition
- diag -> prefix for Diagnosis during the encounter
- historicDiag[nb_days] -> prefix for for history of Diagnosis
- med -> medication dispense
- historicMed[nb_days] -> medication dispense

Data object without prefix would be considered as local variables

## limitation of BPMN

### Sub-process

Sub process can be useful but there is no distinction between a "collapsed" group of elements and a named reference that is defined in its own space
    

### Default

In order to generate testings, default value should be setup to avoid the test case to hold every answers. 

### FEEL language

seem close to what we are looking for BUT it needs to support quantity as CQL and identifier 

G4 file: https://github.com/kiegroup/drools/blob/a8a61af421ede0f14563064523de70b05ed99e33/kie-dmn/kie-dmn-feel/src/main/antlr4/org/kie/dmn/feel/parser/feel11/FEEL_1_1.g4


### BPMN

the DMN feature that enable to open decisions logic should be embedded in BPMN drawings

if implementers want to define questionnaire, the BPM standard does not allowed element such as Select questions in a user friendly manner

## Archive

### Sub-process 

aka: group

- embedded: enable collapse
- event:     
- transaction: enable throw and success/error output

define which Activity or node it implements

