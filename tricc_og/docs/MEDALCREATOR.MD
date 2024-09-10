# Medal creator

## how to read Medal Creator payload

 [this document](./MEDCALCREATOR_PAYLOAD.md) explain the structure of medalcreator payload

## building Steps:

1. read source
1. load all the questions
1. load all the edges
1.1 load the edges edges between the start node and the 'registration_step'
1.1 load the edges from the diagnose
1.1 load the edges to the CC questions for question on the DD without incoming edge 
1. unloop the questions
1. inject the questionsSequence
1. load the questionsSequence edges
1. unloop the questions 

## Exporting Medal Algorithms:

Use the API under:
https://api.medal-creator.wavelab.top/api/v2/algorithms/<project-id>