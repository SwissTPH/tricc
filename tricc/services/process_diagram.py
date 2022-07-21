

from tricc.converters.xml_to_tricc import add_save_calculate, create_activity
from tricc.models import *

from tricc.parsers.xml import read_drawio

import logging



logger = logging.getLogger('default')

def build_tricc_graph(in_filepath):
    pages = {}
    start_page=None
    # read all pages
    logger.info("# Create the activities from diagram pages")
    diagrams = read_drawio(in_filepath)
    for diagram in diagrams:
        logger.debug("Create the activity {0}".format(diagram.attrib.get('name')))
        page = create_activity(diagram)
        if page is not None:
            if page.root is not None:
                pages[page.id] = page
                if page.root.odk_type == TriccExtendedNodeType.start:
                    if start_page is None:
                        start_page = page
                    else:
                        logger.warning(
                            "Page {0} has a start node but there is already a start node in page  {1}"\
                                .format(page.name, start_page.name))
    logger.info("# Create the graph from the start node")
    if start_page is not None:
        # create the graph
        linking_nodes(start_page.root, start_page, pages )
        # Save the calculate list [node]
        calculates = {}
        # save when a calcualte is used dict[name, Dict[id, node]]
        used_calculates = {}
        # save the node that are processed dict[id, node]
        processed_nodes = {}
        
        stashed_nodes = {}
        # add save nodes and merge nodes
        logger.info("# add save calculate")
        walktrhough_tricc_node(start_page.root, add_save_calculate, calculates=calculates,
                               used_calculates=used_calculates, processed_nodes=processed_nodes, stashed_nodes=stashed_nodes)

        while len(stashed_nodes)>0:
            s_node = stashed_nodes.pop(list(stashed_nodes.keys())[0])
            logger.debug("add_save_calculate:unstashed:{}".format(s_node.get_name()))
            walktrhough_tricc_node(s_node, add_save_calculate, calculates=calculates,
                               used_calculates=used_calculates, processed_nodes=processed_nodes, stashed_nodes=stashed_nodes)
        logger.info("# check if all edges (arrow where used)")
        for key, page in pages.items():
            if page.edges is not None and len(page.edges)>0:
                logger.warning(
                    "Page {0} has still {1}/{2} edges that were not used: {3}"\
                    .format(page.label, len(page.edges) ,len(page.edges_copy),page.edges ))
         # refresh the edges (were remove by previous code)
        return start_page
        
    else:
        logger.warning("start page not found")
    # Q. how to handle graph output
        # hardlink with out edge: create a fake node
        # or should we always create that fake node
        # *** or should we enfore "next activity node" ****
        # 
    
    # do the calculation, expression ...


    
    
def linking_nodes(node, page, pages, processed_nodes = [], path = []):
    # get the edges that have that node as source
    node_edge = list(filter(lambda x: (x.source == node.id) , page.edges))
    node.activity = page
    #build current path
    current_path = path + [node.id]
    # don't stop the walkthroug by default
    logger.debug("linking node {0}".format(node.get_name()))
    # clean name
    if hasattr(node, 'name') and node.name is not None and node.name.endswith('_'):
        node.name = node.name + node.id
    if len(node_edge) == 0:
        logger.debug("node {0} without edges out found in page {1}, full path {2}"\
            .format(node.get_name(), page.label, current_path))
    for edge in node_edge:
        #get target node
        if edge.target in page.nodes:
            target_node = page.nodes[edge.target]
                            # link perv / next nodes
            # walk only if the target node was not processed already
            if edge.target not in processed_nodes:
                if target_node.odk_type == TriccExtendedNodeType.goto:
                    next_page = walkthrough_goto_node(target_node, page, pages, processed_nodes, current_path)
                # set next page as node to link the next_node of the activity
                    if next_page is not None:
                        target_node = next_page
                elif target_node.odk_type == TriccExtendedNodeType.link_out:
                    link_out = walkthrough_link_out_node( target_node, page, pages, processed_nodes, current_path)
                    if link_out is not None:
                        target_node = link_out
                elif issubclass(target_node.__class__, TriccNodeSelect):
                    for key, option in target_node.options.items():
                        linking_nodes(option, page, pages, processed_nodes, current_path)

                # don't save the link out because the real node is the page
                processed_nodes.append(target_node.id)
                linking_nodes(target_node, page, pages, processed_nodes, current_path)
            elif edge.target in current_path:
                logger.warning("possible loop detected for node {0} in page {1}; path: {2} ".format(node.get_name(), page.label, current_path))
            if isinstance(node, TriccNodeSelectNotAvailable):
                set_prev_next_node( node.options[0], target_node)
            else:  
                set_prev_next_node( node, target_node)
        else:
            logger.warning("target not found {0}".format(edge.target))
        page.edges.remove(edge)
  

      
def walkthrough_goto_node(node, page, pages, processed_nodes, current_path):
     # find the page
    if node.link in pages:
        next_page = pages[node.link]
        # walk thought the next page
        if next_page.id not in processed_nodes:
        # will be added in process nod later
        # add the id to avoid loop: 
            logger.debug("jumping to page {0}".format(next_page.label))
        if int(next_page.instance) != int(node.instance):
            #FIXME find if there is other instance (list in activity ?)
            # must look in pages thans to base_instance
            next_page = next_page.make_instance(node.instance)
            pages[next_page.id]=next_page
        linking_nodes(next_page.root, next_page, pages, processed_nodes, current_path)
        # attach the page
        #for got_to_prev_nodes in node.prev_nodes:
        #    set_prev_next_node(got_to_prev_nodes, next_page, node )
        # steal the edges
        replace_node(node, next_page, page)
                
        # continue on the initial page
        return next_page
    else:
        logger.warning("node {0} from page {1} doesnot have a valid link".format(node.label, page.label))



def walkthrough_link_out_node(node, page, pages, processed_nodes, current_path):
    if node.reference is not None:
        link_in_list=[]
        link_in_page=None
        for page in pages:
            link_in_list += list(filter(lambda x: (x.name == node.reference) , page.nodes))
            #save the first page wheere a link is found to continue the walktrhough
            if len(link_in_list)>0 and link_in_page is None:
                link_in_page = page
        if len(link_in_list) == 0:
            logger.warning("link in {0} not found for link out {1} in page {2}"\
                .format(node.reference, node.name,page.label))
        elif len(link_in_list) > 1:
            logger.warning("more than one link in {0} found for link out {1} in page {2}"\
                .format(node.reference, node.name,page.label))
        else:
            # all good, only one target node found
            linked_target_node=link_in_list[0]
            # steal the edges
            replace_node(node, linked_target_node, page)
            
            if linked_target_node.id not in processed_nodes:
                linking_nodes(linked_target_node, link_in_page, pages, processed_nodes, current_path)
    else:
            logger.warning("link out {0} in page {1} : reference not found"\
                .format(node.name,page.label))


