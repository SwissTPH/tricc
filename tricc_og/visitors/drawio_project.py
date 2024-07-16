import logging
from tricc_og.models.base import (
    TriccBaseModel,
    TriccMixinRef,
    add_flow,
    to_scv
)
from tricc_og.models.tricc import TriccNodeType
from tricc_og.builders.utils import generate_id
logger = logging.get_logger(__name__)
## Process edges


def process_nodes(project):
    for elm, data in project.graph.nodes(data=True):
        if elm.type_scv == to_scv(TriccNodeType.select_yesno):
            get_yesno_options(project, elm)


def get_yesno_options(project, select_node):
    for k, v in {1: 'yes', 2: 'no'}.items():
        option = TriccBaseModel(
                code=v,
                system=select_node.get_name(),
                type_scv=TriccMixinRef(
                    system="tricc_type",
                    code=str(TriccNodeType.select_option)
                ),
                label=project.get_keyword_trad(v),
                attributes={
                    "id": generate_id(),
                },
            )
        # FIXME attributtes


def process_edges(project):
    for u, v, attrs in project.graph.edges(data=True):
        if u.type_scv == to_scv(TriccNodeType.select_yesno):
            process_yesno_edge(project, u, v, attrs)
            
def process_yesno_edge(u, v, attrs):            
    if 'label' in attrs:
        if attrs['label'] == project.get_keyword_trad('yes'):
            pass
    else:
        logger.error(f"edge between {u} and {v} in context {attrs['context']} does not have a label")


def process_factor_edge(edge, nodes):
    factor = edge.value.strip()
    if factor != 1:
        return TriccNodeCalculate(
            id=edge.id,
            expression_reference="number(${{{}}}) * {}".format("", factor),
            reference=[nodes[edge.source]],
            activity=nodes[edge.source].activity,
            group=nodes[edge.source].group,
            label="factor {}".format(factor),
        )
    return None


def process_condition_edge(edge, nodes):
    label = edge.value.strip()
    for op in OPERATION_LIST:
        if op in label:
            # insert rhombus
            return TriccNodeRhombus(
                id=edge.id,
                reference=[nodes[edge.source]],
                path=nodes[edge.source],
                activity=nodes[edge.source].activity,
                group=nodes[edge.source].group,
                label=label,
            )


def process_exclusive_edge(edge, nodes):
    error = None
    if issubclass(nodes[edge.source].__class__, TriccNodeCalculateBase):
        # insert Negate
        if not isinstance(nodes[edge.target], TriccNodeExclusive) or not isinstance(
            nodes[edge.source], TriccNodeExclusive
        ):
            return TriccNodeExclusive(
                id=edge.id,
                activity=nodes[edge.target].activity,
                group=nodes[edge.target].group,
            )
        else:
            error = "No after or before a exclusice/negate node"
    else:
        error = "label not after a yesno nor a calculate"
    if error is not None:
        logger.warning(
            "Edge between {0} and {1} with label '{2}' could not be interpreted: {3}".format(
                nodes[edge.source].get_name(),
                nodes[edge.target].get_name(),
                edge.value.strip(),
                error,
            )
        )
    return None


def process_yesno_edge(edge, nodes):
    if edge.value is None:
        logger.error(
            "yesNo {} node with labelless edges".format(nodes[edge.source].get_name())
        )
        exit()
    label = edge.value.strip().lower()
    yes_option = None
    no_option = None
    for option in nodes[edge.source].options.values():
        if option.name == "1":
            yes_option = option
        else:
            no_option = option
    if label.lower() in TRICC_FOLOW_LABEL:
        pass
    elif label.lower() in TRICC_YES_LABEL:
        edge.source = yes_option.id
    elif label.lower() in TRICC_NO_LABEL:
        edge.source = no_option.id
    else:
        logger.warning(
            "edge {0} is coming from select {1}".format(
                edge.id, nodes[edge.source].get_name()
            )
        )
