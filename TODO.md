#. update the import strategy

- load the QS as activity but only with scv reference of the node, having all the node on the authored graph is enough
- load the Diagnostic as activity but only with scv reference of the node, having all the node on the authored graph is enough
- the authored graph should just be mandatory question + diagnoses
- add the diagnoses as output of the diagnoses

#. create  layout strategy

- move the implementation graph making there


#. create export strategy

- make the context logic:

when an activity start node is met, generate the "operation" for its applicability: an OR is place between its different inputs, each inputs is ( previous node condition) & applicability of the Activity that had defined that edges

#. update the docs

- Scheduler, schedule events
- events have activity, tasks and edges
- activities have activities, task and edges
- task have only 1 stage (cpg-common-process), task might be part of several activities
- stage have only tasks
- edges have condition, source (A/T) , Target and Activity
- in the implementation graph the activities become context, task sorted by stage