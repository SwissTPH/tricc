from tricc.models import *


def set_prev_next_node( source_node, target_node):
    # if it is end node, attached it to the activity/page
    set_prev_node( source_node, target_node)
    source_node.next_nodes.append(target_node)

def set_prev_node( source_node, target_node):
    #update the prev node of the target not if not an end node
    if target_node.odk_type == TriccExtendedNodeType.end:
        source_node.activity.end_prev_nodes.append(source_node)
    elif target_node.odk_type == TriccExtendedNodeType.activity_end:
        source_node.activity.activity_end_prev_nodes.append(source_node)
    else:
        # update directly the prev node of the target
        target_node.prev_nodes.append(source_node)


def walktrhough_tricc_node( node, callback, **kwargs):
        callback(node, **kwargs)
        # if has next, walkthrough them (support options)
        if node.odk_type == TriccExtendedNodeType.activity:
            if node.root is not None:
                walktrhough_tricc_node(node.root, callback, **kwargs)
        elif issubclass(node.__class__, TriccNodeSelect):
            for key, option in node.options.items():
                walktrhough_tricc_node(option, callback, **kwargs)
        if hasattr(node,'next_nodes') and len(node.next_nodes)>0:
            for next_node in node.next_nodes:
                walktrhough_tricc_node(next_node, callback, **kwargs)