from tricc_og.strategies.transform.base_transform_strategy import BaseTransformStrategy
from tricc_og.visitors.tricc_project import (
    get_element,
    add_flow,
    save_graphml,
    hierarchical_pos,
    unloop_from_node,
    import_mc_flow_from_activities,
    make_implementation,
)
from tricc_og.models.base import TriccMixinRef
from tricc_og.models.trigger import TriccTriggers

import logging
logger = logging.getLogger("default")


class UnlooopStrategy(BaseTransformStrategy):
    code_system = None
    
    @classmethod
    def __init__(cls, project, **kwargs):
        super(cls, UnlooopStrategy).__init__(project, **kwargs)
        cls.code_system = cls.project.code_system
    
    def _create_flat_order(self):
        flat_order = []
        root_concept = next((c for c in self.code_system.concept if c.code == '__root__'), None)
        
        if root_concept:
            root_order = next((p.valueString for p in root_concept.property if p.code == "order"), "")
            root_members = root_order.split(',')
            
            for member in root_members:
                flat_order.extend(self._visit_concept(member))
        
        return flat_order

    def _visit_concept(self, concept_code):
        concept = next((c for c in self.code_system.concept if c.code == concept_code), None)
        if not concept:
            return []
        
        result = [concept_code]
        order_property = next((p for p in concept.property if p.code == "order"), None)
        
        if order_property:
            children = order_property.valueString.split(',')
            for child in children:
                result.extend(self._visit_concept(child))
        
        return result
        
    def execute(self, **kwargs):
        ### TRANSFORM
        order = self._create_flat_order()
        project = self.project
        make_implementation(project)
        logger.info(f"implementing graph have {project.impl_graph.number_of_edges()} edges")
        for trigger in TriccTriggers:
            start_scv = TriccMixinRef(
                    code=str(trigger),
                    system="cpg-common-processes"
                ).scv()
            if start_scv in project.graph.nodes:
                start = project.graph.nodes[start_scv]['data']
                for start_impl in start.instances:
                    save_graphml(project.graph, start.scv(), "graph")
                    # image
                    #self.save_simple_graph(project.impl_graph, start_impl, "loaded.png")
                    unloop_from_node(project.impl_graph, start_impl, order)
                    logger.info(f"Unlooped graph has {project.impl_graph.number_of_edges()} edges")
                    # image
                    #self.save_simple_graph(project.impl_graph, start_impl, "unlooped.png")
                    import_mc_flow_from_activities(
                            project, start_impl, order
                        )
                    # image
                    # self.save_simple_graph(project.impl_graph, start_impl, "qs_loaded.png")
                    # self.save_simple_tree(project.impl_graph, start_impl.scv(), "tree.png")
                    # save_graphml(project.impl_graph, start_impl.scv(), "decisiontree.graphml")
                    logger.info(f"Final graph has {project.impl_graph.number_of_edges()} edges")

