from bpmn_python import bpmn_diagram_rep as diagram

def add_node(graph, bpmn_graph, scv, process_id):
    node = graph.nodes[scv]['data']
    label = node.label
    bpmn_graph.add_task_to_diagram(process_id, task_name=label, node_id=scv)

      
def create_bpmn_from_dict(graph, keys=False):
    bpmn_graph = diagram.BpmnDiagramGraph()
    bpmn_graph.create_new_diagram_graph(diagram_name="Process")

    process_id = bpmn_graph.add_process_to_diagram()
    processed_node = set()
    # Map nodes to BPMN elements


    # Map edges to BPMdN sequence flows
    for edge in graph.edges(keys=keys, data=True):
        if edge[0] not in processed_node:
            add_node(graph, bpmn_graph, edge[0], process_id)
        if edge[1] not in processed_node:
            add_node(graph, bpmn_graph, edge[1], process_id)
        bpmn_graph.add_sequence_flow_to_diagram(process_id, edge[0], edge[1], "")

    return bpmn_graph

