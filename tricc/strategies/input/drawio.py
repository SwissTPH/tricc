

import logging
import os
from copy import copy

from tricc.converters.xml_to_tricc import create_activity
from tricc.visitors.tricc import process_calculate
from tricc.models.tricc import *
from tricc.strategies.input.base_input_strategy import BaseInputStrategy
from tricc.parsers.xml import read_drawio
logger = logging.getLogger('default')
class DrawioStrategy(BaseInputStrategy):
    processes = [
        'triage',
        'registration',
        'emergency-care',
        'local-urgent-care',
        'actue-tertiary-care',
        'history-and-physical',
        'diagnostic-testing',
        'determine-diagnosis',
        'provide-counseling',
        'dispense-medications',
        'monitor-and-follow-up-of-patient',
        'alerts-reminders-education',
        'discharge-referral-of-patient',
        'charge-for-service',
        'record-and-report'    
    ]
    def process_pages(self, start_page, pages):
        # create the graph
        self.linking_nodes(start_page.root, start_page, pages )
        # Save the calculate list [node]
        calculates = {}
        # save when a calcualte is used dict[name, Dict[id, node]]
        used_calculates = {}
        
        # save the node that are processed dict[id, node]
        
        # add save nodes and merge nodes
        stashed_node_func( start_page.root, process_calculate, used_calculates=used_calculates, calculates =calculates, recusive=False )
        
            
        logger.info("# check if all edges (arrow) where used")
        for key, page in pages.items():
            if page.unused_edges is not None and len(page.unused_edges)>0:
                logger.warning(
                    "Page {0} has still {1}/{2} edges that were not used:"\
                    .format(page.label, len(page.unused_edges) ,len(page.edges)))
        # refresh the edges (were remove by previous code)
        return pages
        
    
    
    def execute(self, in_filepath, media_path):
        files = []
        pages = {}
        diagrams = []
        start_pages= {}
        # read all pages
        logger.info("# Create the activities from diagram pages")
        if os.path.isdir(in_filepath):
            files = [f for f in os.listdir(in_filepath) if f.endswith('.drawio')]
        elif os.path.isfile(in_filepath):
            files = [in_filepath]
        else:
            logger.error(f"no input file found at {in_filepath}")
            exit()
        for file in files:
            diagrams += read_drawio(file)

        for diagram in diagrams:
            logger.info("Create the activity {0}".format(diagram.attrib.get('name')))
            page = create_activity(diagram, media_path)
            if page is not None:
                if page.root is not None:
                    pages[page.id] = page
                    if page.root.tricc_type == TriccNodeType.start:
                        if 'main' not in start_pages and (page.root.process == 'main' or page.root.process is None):
                            start_pages['main'] = page
                        elif page.root.process is not None:
                            if page.root.process not in start_pages:
                                start_pages[page.root.process] = []
                            start_pages[page.root.process].append(page)
                        else:
                            logger.warning(
                                "Page {0} has a start node but there is already a start node in page  {1}"\
                                    .format(page.label, start_page.label))
        logger.info("# Create the graph from the start node")
        
        app = self.execute_linked_process(start_pages,pages)
        if app:
            start_pages['main'] = app
            pages[app.id]= app
            pages = self.process_pages(app, pages)
            
            return start_pages, pages
        elif start_pages:
            for process in start_pages:
                if isinstance(start_pages[process], list):
                    for page_to_process in start_pages[process]:
                        pages = self.process_pages(page_to_process, pages)
                else:
                    pages = self.process_pages(start_pages[process], pages)
            return start_pages, pages
            
        else:
            logger.warning("start page not found")
        # Q. how to handle graph output
            # hardlink with out edge: create a fake node
            # or should we always create that fake node
            # *** or should we enfore "next activity node" ****
            # 
        
        # do the calculation, expression ...


        
    def linking_nodes(self,node, page, pages, processed_nodes = [], path = []):
        # get the edges that have that node as source
        
        node_edge = list(filter(lambda x: (x.source == node.id or x.source == node) , page.edges))
        node.activity = page
        #build current path
        current_path = path + [node.id]
        # don't stop the walkthroug by default
        logger.debug("linking node {0}".format(node.get_name()))
        #FIXME remove note
        if len(node_edge) == 0 and not issubclass(node.__class__, (TriccNodeCalculateBase, TriccNodeSelectOption,TriccNodeActivity, TriccNodeNote)):
            if issubclass(node.__class__, TriccNodeSelect):
                option_edge = list(filter(lambda x: (lambda y: x.source == y.id, node.options) , page.edges))
                if len(option_edge) == 0:
                    logger.error("node {0} without edges out found in page {1}, full path {2}"\
                        .format(node.get_name(), page.label, current_path))
            else:                  
                logger.error("node {0} without edges out found in page {1}, full path {2}"\
                    .format(node.get_name(), page.label, current_path))
                exit()
        for edge in node_edge:
            #get target node
            if edge.target in page.nodes:
                target_node = page.nodes[edge.target]
                                # link perv / next nodes
                # walk only if the target node was not processed already
                if target_node  not in processed_nodes:
                    if isinstance(target_node, TriccNodeActivity):
                        self.linking_nodes(target_node.root, target_node, pages, processed_nodes, current_path)
                    elif isinstance(target_node, TriccNodeGoTo):
                        next_page = self.walkthrough_goto_node(target_node, page, pages, processed_nodes, current_path)
                        #update reference
                        #FIXME support reference str
                        for n in page.nodes:
                            sn = page.nodes[n]
                            if issubclass(sn.__class__, TriccRhombusMixIn) and isinstance(sn.reference,list) and target_node in sn.reference:
                                sn.reference.remove(target_node)
                                sn.reference.append(next_page)
                    # set next page as node to link the next_node of the activity
                        if next_page is not None:
                            target_node = next_page
                    elif isinstance(target_node, TriccNodeLinkOut):
                        link_out = self.walkthrough_link_out_node( target_node, page, pages, processed_nodes, current_path)
                        if link_out is not None:
                            target_node = link_out
                    elif issubclass(target_node.__class__, TriccNodeSelect):
                        for key, option in target_node.options.items():
                            self.linking_nodes(option, page, pages, processed_nodes, current_path)
                    if target_node  not in processed_nodes:
                    # don't save the link out because the real node is the page
                        processed_nodes.append(target_node)
                    self.linking_nodes(target_node, page, pages, processed_nodes, current_path)
                elif edge.target in current_path:
                    logger.warning("possible loop detected for node {0} in page {1}; path:".format(node.get_name(), page.label))
                    for node_id in current_path:
                        node = get_node_from_list(processed_nodes,node_id)
                        if node is not None:
                            logger.warning(node.get_name())
                if isinstance(node, TriccNodeSelectNotAvailable):
                    set_prev_next_node( node.options[0], target_node)
                else:  
                    set_prev_next_node( node, target_node)
            else:
                logger.warning("target not found {0} for node {1}".format(edge.target, node.get_name()))
            #page.edges.remove(edge)
    

        
    def walkthrough_goto_node(self,node, page, pages, processed_nodes, current_path):
        # find the page
        if node.link in pages:
            next_page = pages[node.link]
            # walk thought the next page
            max_instance = 1
            if node.instance == 0 or next_page.root.instance == 0:
                for other_page in next_page.instances.values():
                    if int(other_page.instance) > int(max_instance):
                        max_instance = other_page.instance
                #auto instance starts at 101
                next_page = next_page.make_instance(max(100,max_instance)+1)
            else:
                #return existing instance if any
                next_page = next_page.make_instance(node.instance)
            if next_page.id not in pages:
                pages[next_page.id]=next_page
            logger.debug("jumping to page {0}::{1} from {2}".format(next_page.label, next_page.instance, node.get_name()))
            if next_page not in processed_nodes:
                self.linking_nodes(next_page.root, next_page, pages, processed_nodes, current_path)
            
            replace_node(node, next_page, page)   
                    
            # continue on the initial page
            return next_page
        else:
            logger.warning("node {0} from page {1} doesnot have a valid link".format(node.label, page.label))



    def walkthrough_link_out_node(self,node, page, pages, processed_nodes, current_path):
        if node.reference is not None:
            link_in_list=[]
            link_in_page=None
            for page in pages:
                link_in_list += list(filter(lambda x: (x.name == node.reference) , page.nodes))
                #save the first page where a link is found to continue the walktrhough
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
                
                if linked_target_node not in processed_nodes:
                    self.linking_nodes(linked_target_node, link_in_page, pages, processed_nodes, current_path)
                return linked_target_node
        else:
                logger.warning("link out {0} in page {1} : reference not found"\
                    .format(node.name,page.label))


