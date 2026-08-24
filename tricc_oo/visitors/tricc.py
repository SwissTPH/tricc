import re
import logging
import requests
import base64
from collections import defaultdict
from typing import Optional
from tricc_oo.visitors.text_injection import TEXT_INJECTION_FIELDS

from tricc_oo.models.base import get_repeat
from tricc_oo.converters.utils import generate_id
from tricc_oo.models.base import (
    TriccBaseModel, TriccNodeType, TriccGroup,
    TriccOperator, TriccOperation, TriccStatic, TriccReference, not_clean,
    and_join, or_join, clean_or_list, nand_join, TriccEdge
)
from tricc_oo.models.ordered_set import OrderedSet
from tricc_oo.models.calculate import (
    TriccNodeDisplayBridge,
    TriccNodeBridge,
    TriccNodeWait,
    TriccNodeCalculate,
    TriccNodeRhombus,
    TriccNodeFactor,
    TriccNodeDisplayCalculateBase,
    TriccNodeExclusive,
    TriccNodeProposedDiagnosis,
    TriccNodeCount,
    TriccNodeAdd,
    TriccNodeFakeCalculateBase,
    TriccRhombusMixIn,
    TriccNodePopulate,
    TriccNodeActivityEnd,
    TriccNodeActivityStart,
    TriccNodeEnd,
    TriccNodeDiagnosis,
    get_node_from_id,

)
from tricc_oo.models.tricc import (
    TriccNodeCalculateBase, TriccNodeActivity, TriccNodeBaseModel, TriccNodeNumber,
    TriccNodeSelectMultiple,
    TriccNodeSelectOne,
    TriccNodeSelectOption,
    TriccNodeSelectYesNo,
    TriccNodeInputModel,
    TriccNodeSelect,
    TriccNodeSelectNotAvailable,
    TriccNodeMoreInfo,
    TriccNodeDisplayModel,
    TriccNodeMainStart,
    TriccNodeAcceptDiagnostic,
    TRICC_FALSE_VALUE,
    TRICC_TRUE_VALUE,
)
from tricc_oo.visitors.utils import PROCESSES
from tricc_oo.converters.cql_to_operation import transform_cql_to_operation
from tricc_oo.converters.datadictionnary import lookup_codesystems_code
from tricc_oo.converters.tricc_to_xls_form import get_list_names, get_export_name

logger = logging.getLogger("default")
ONE_QUESTION_AT_A_TIME = False
NO_LABEL = "__NO_LABEL__"
# Track the last group that was reordered to avoid unnecessary reordering
_last_reordered_group = None


def merge_node(from_node, to_node):
    if from_node.activity != to_node.activity:
        logger.critical("Cannot merge nodes from different activities")
    elif issubclass(from_node.__class__, TriccNodeCalculateBase) and issubclass(
        to_node.__class__, TriccNodeCalculateBase
    ):
        for e in to_node.activity.edges:
            if e.target == from_node.id:
                e.target = to_node.id
    else:
        logger.critical("Cannot merge not calculate nodes ")


def get_max_version(dict):
    max_version = None
    for id, sim_node in dict.items():
        if max_version is None or max_version.version < sim_node.version:
            max_version = sim_node
    return max_version


def get_versions(name, iterable, repeat=None):
    return [n for n in iterable if version_filter(name, repeat)(n)]


def version_filter(name, repeat=None):
    """Match nodes by name (+ optional repeat slot) for versioning / reference lookup.

    Does not special-case ``repeat=-1``: those nodes stay resolvable by reference.
    Value inheritance excludes ``-1`` separately when building GET_INHERITED_VALUE.
    """
    from tricc_oo.models.base import get_repeat as _get_repeat

    def _matches(item):
        if isinstance(item, TriccNodeSelectOption):
            return False
        if isinstance(item, TriccNodeEnd):
            return name == item.get_reference()
        if not hasattr(item, "name") or item.name != name:
            return False
        if repeat is not None:
            return _get_repeat(item) == repeat
        return True

    return _matches


def _get_defining_expression_op(expr):
    """Peel off inheritance/merge wrappers (COALESCE, GET_INHERITED_VALUE) to reach
    the original local/definition expression op for a calculate node.
    This ensures versions that share the same *formula* (before any inheritance merge)
    get the same origin signature even after wrappers have been applied.
    """
    if not isinstance(expr, TriccOperation):
        return expr
    wrappers = {TriccOperator.COALESCE, TriccOperator.GET_INHERITED_VALUE}
    current = expr
    guard = 0
    while (
        isinstance(current, TriccOperation)
        and current.operator in wrappers
        and current.reference
        and guard < 8
    ):
        guard += 1
        first = current.reference[0] if isinstance(current.reference, (list, tuple)) else None
        if isinstance(first, TriccOperation):
            current = first
        else:
            break
    return current


def group_prev_versions_by_origin_signature(name, expression, prev_versions):
    """Group previous versions (same name + repeat) by the origin signature
    (cleaned reference-only repr) of their *defining* expression.

    Elements in each list bucket will later contribute via
    TriccOperation(GET_INHERITED_VALUE, bucket_list).

    The resulting per-bucket GET ops are then fed to the existing
    datatype-aware merge_expressions so that "values of the dict" still
    follow the old boolean/number/etc merge rules.
    """
    expression_sig = hash(repr(expression.origin if expression.origin else name))
    sibling = []
    groups = defaultdict(list)
    for pv in (prev_versions or []):
        expr = getattr(pv, "expression", None) or getattr(pv, "expression_reference", None)
        if expr:
            
            sig = hash(repr(getattr(expr, "origin", expr)))
        else:
            sig = hash(repr(expr.origin) if expr.origin else name)
        if sig == expression_sig:
            sibling.append(pv)
        else:
            groups[sig].append(pv)
    return list(sibling), dict(groups)


def get_last_version(name, processed_nodes, _list=None, repeat=None):
    max_version = None
    if isinstance(_list, dict):
        _list = _list[name].values() if name in _list else []
    if _list is None:
        if isinstance(processed_nodes, OrderedSet):
            return processed_nodes.find_last(version_filter(name, repeat))
        else:
            _list = get_versions(name, processed_nodes, repeat)
    if _list:
        for sim_node in _list:
            # get the max version while not taking a node that have a next node before next calc
            if (
                max_version is None
                or max_version.activity.path_len < sim_node.activity.path_len
                or max_version.path_len < sim_node.path_len
                or (max_version.path_len == sim_node.path_len and hash(max_version.id) < hash(sim_node.id))
            ):
                max_version = sim_node
    if not max_version:
        already_processed = [
            p_node for p_node in _list
            if version_filter(name, repeat)(p_node)
        ]
        if already_processed:
            max_version = sorted(already_processed, key=lambda x: x.path_len, reverse=False)[0]

    return max_version


# main function to retrieve the expression from the tree
# node is the node to calculate
# processed_nodes are the list of processed nodes
def get_node_expressions(node, processed_nodes, process=None):
    get_overall_exp = issubclass(
        node.__class__,
        (TriccNodeDisplayCalculateBase, TriccNodeProposedDiagnosis, TriccNodeDiagnosis, TriccNodeActivity)
    ) and not isinstance(node, (TriccNodeDisplayBridge))
    expression = None
    # in case of recursive call processed_nodes will be None
    if processed_nodes is None or is_ready_to_process(node, processed_nodes=processed_nodes):
        expression = get_node_expression(
            node, processed_nodes=processed_nodes, get_overall_exp=get_overall_exp, process=process
        )
    if (
        issubclass(node.__class__, TriccNodeCalculateBase)
        and not isinstance(expression, (TriccStatic, TriccReference, TriccOperation))
        and str(expression) != ""
        and not isinstance(node, (TriccNodeWait, TriccNodeActivityEnd, TriccNodeActivityStart, TriccNodeEnd))
    ):
        # No substitution: a calculate whose expression cannot be derived must stay
        # visibly absent rather than silently become a constant `true` — the output
        # strategies decide what an absent expression means for their format
        # (fix/20260821-output-pass-calculate-readiness.md).
        logger.warning("Calculate {0} returning no calculations".format(node.get_name()))
        expression = None
    return expression


def _filter_inheritable_versions(versions):
    """Drop repeat=-1 nodes from value-inheritance operand lists.

    Those nodes remain addressable for references / version numbering, but must
    not contribute to GET_INHERITED_VALUE / coalesce inheritance.
    """
    return [v for v in (versions or []) if get_repeat(v) != -1]


def _export_version_bucket_key(name, repeat):
    """Group key for nodes that share an export base name.

    ``get_export_name`` only serialises ``_Rr_<n>`` when ``repeat > 1``.
    Therefore ``repeat <= 1`` (including ``-1`` and default ``1``) share one
    export base and must share one version number space to avoid
    ``name_Vv_1`` collisions across slots.
    """
    if repeat is not None and int(repeat) > 1:
        return (name, int(repeat))
    return (name, "<=1")


def export_version_filter(name, node_repeat):
    """Match nodes that share the same export base name as (name, node_repeat)."""

    def _matches(item):
        if isinstance(item, TriccNodeSelectOption):
            return False
        if isinstance(item, TriccNodeEnd):
            if name != item.get_reference():
                return False
            # Ends participate in the default export pool
            return _export_version_bucket_key(name, node_repeat if node_repeat is not None else 1)[1] == "<=1"
        if not hasattr(item, "name") or item.name != name:
            return False
        return _export_version_bucket_key(name, get_repeat(item)) == _export_version_bucket_key(
            name, node_repeat if node_repeat is not None else 1
        )

    return _matches


def get_export_version_peers(name, node_repeat, iterable, exclude=None):
    """Return nodes that would collide in export name without unique versions."""
    filt = export_version_filter(name, node_repeat)
    return [n for n in iterable if n is not exclude and filt(n)]


def set_last_version_false(node, processed_nodes):
    """Mark prior export-name peers as not-last and assign unique versions.

    Peers are nodes that share the same export base (same name; same ``repeat``
    when ``repeat > 1``, else all ``repeat <= 1`` including ``-1``). This keeps
    ODK survey names unique when ``_Rr_`` is omitted for low/negative repeats.
    """
    if isinstance(node, (TriccNodeSelectOption)):
        return
    from tricc_oo.models.base import get_repeat

    node_name = node.name if not isinstance(node, TriccNodeEnd) else node.get_reference()
    node_repeat = None if isinstance(node, TriccNodeEnd) else get_repeat(node)

    if isinstance(processed_nodes, OrderedSet):
        last_version = processed_nodes.find_prev(node, export_version_filter(node_name, node_repeat))
    else:
        peers_all = get_export_version_peers(node_name, node_repeat, processed_nodes, exclude=node)
        last_version = None
        if peers_all:
            last_version = sorted(
                peers_all,
                key=lambda n: (
                    getattr(n, "path_len", 0) or 0,
                    getattr(n, "version", 0) or 0,
                    str(getattr(n, "id", "")),
                ),
            )[-1]

    if last_version and getattr(node, "process", "") != "pause":
        peers = get_export_version_peers(node_name, node_repeat, processed_nodes, exclude=node)
        # Stable order: path then existing version then id
        peers_ordered = sorted(
            peers,
            key=lambda n: (
                getattr(n, "path_len", 0) or 0,
                getattr(n, "version", 0) or 0,
                str(getattr(n, "id", "")),
            ),
        )
        for i, prev in enumerate(peers_ordered, start=1):
            prev.last = False
            prev.version = i
            # Invalidate cached export name so _Vv_ suffix is recomputed
            if hasattr(prev, "export_name"):
                prev.export_name = None
        node.version = len(peers_ordered) + 1
        if hasattr(node, "export_name"):
            node.export_name = None
        node.path_len = max(node.path_len or 0, (last_version.path_len or 0) + 1)
    return last_version


def get_version_inheritance(node, all_prev_versions, processed_nodes):

    # Updated to merge ALL previous versions, not just the last one
    # This ensures inheritance works even when intermediate activities weren't triggered

    if (isinstance(node, TriccNodePopulate) and node.context == "history"):
        node.last = True
        return
    # repeat=-1: local-only capture — versioning still runs via set_last_version_false,
    # but this node does not inherit values from prior versions.
    if get_repeat(node) == -1:
        return
    # Prior repeat=-1 nodes are never inheritance sources
    all_prev_versions = _filter_inheritable_versions(all_prev_versions)
    if not all_prev_versions:
        return
    if not issubclass(node.__class__, (TriccNodeInputModel)):
        node.last = True
        if issubclass(node.__class__, (TriccNodeDisplayCalculateBase, TriccNodeEnd)) and node.name is not None:
            # logger.debug("set last to false for node {}
            # and add its link it to next one".format(last_used_calc.get_name()))
            if node.prev_nodes:
                # Set prev_next_node only with the immediate last version
                for pv in all_prev_versions:
                    set_prev_next_node(pv, node)
            else:
                expression = node.expression or node.expression_reference or getattr(node, "relevance", None)
                # NEW calculate inheritance approach:
                # Group prev versions (same repeat) by the origin signature of their defining expression.
                # Contribute each group via GET_INHERITED_VALUE( list_of_same_sig_nodes ).
                # Then feed those group values into the *existing* datatype merge logic.
                if all_prev_versions and isinstance(expression, TriccOperation):
                    siblings, groups = group_prev_versions_by_origin_signature(node.name, expression, all_prev_versions)
                    contribs = [
                        TriccOperation(TriccOperator.GET_INHERITED_VALUE, plist)
                        for plist in groups.values() if plist
                    ]
                    main_expression = TriccOperation(TriccOperator.GET_INHERITED_VALUE, [expression, *siblings])
                    if contribs:
                        if len(contribs) == 1:
                            expression = merge_expressions(main_expression, contribs[0])
                        else:
                            expression = merge_expressions(main_expression, contribs[0], *contribs[1:])
                    # else: no change, expression stays as local
                else:
                    # Original path for relevance, Ends, or non-op expressions
                    if all_prev_versions and expression:
                        expression = merge_expressions(expression, *all_prev_versions)
                    elif len(all_prev_versions) == 1:
                        expression = all_prev_versions[0]
                    elif all_prev_versions:
                        expression = merge_expressions(*all_prev_versions)
                if node.expression:
                    node.expression = expression
                elif node.expression_reference:
                    node.expression_reference = expression
                elif getattr(node, 'relevance', None):
                    node.relevance = expression
    else:
        node.last = False

        # Create a calculate node that coalesces all previous saved values with the current node value
        calc_id = generate_id(f"save_{node.save}")
        
        # Build reference list with current node and all previous versions
        reference_list = [node] + all_prev_versions if all_prev_versions else []
        
        calc = TriccNodeCalculate(
            id=calc_id,
            name=node.save,
            path_len=node.path_len + 1,
            expression_reference=TriccOperation(
                TriccOperator.COALESCE,
                reference_list,
            ),
            reference=reference_list,
            activity=node.activity,
            group=node.group,
            label=f"Save calculation for {node.label}",
            last=True,
        )
        node.activity.nodes[calc.id] = calc
        node.activity.calculates.append(calc)
        # set_last_version_false(calc, processed_nodes)
        processed_nodes.add(calc)
        if issubclass(node.__class__, TriccNodeInputModel):
            # Coalesce with all previous versions
            inheritance_operands = (all_prev_versions if all_prev_versions else [])
            node.expression = TriccOperation(TriccOperator.GET_INHERITED_VALUE, inheritance_operands)


def merge_expressions(expression, last_version, *argv):
    priors = [last_version] + list(argv)
    datatype = expression.get_datatype()

    def has_input_ref(node_or_op):
        if issubclass(node_or_op.__class__, (TriccNodeInputModel, TriccNodeSelect)):
            return True
        if hasattr(node_or_op, 'get_references') and node_or_op.get_references():
            return any(has_input_ref(r) for r in node_or_op.get_references() if r != node_or_op)
        return False

    all_nodes = [expression] + priors
    has_inputs = any(has_input_ref(n) for n in all_nodes if hasattr(n, 'get_references') or issubclass(type(n), TriccNodeBaseModel))

    if datatype == "boolean":
        return or_join([expression] + [TriccOperation(TriccOperator.ISTRUE, [p]) for p in priors])
    elif has_inputs and datatype in ("number", "integer"):
        summed = TriccOperation(TriccOperator.PLUS, priors + [expression])
        return TriccOperation(TriccOperator.COALESCE, [summed])
        # Coalesce: inputs/values/strings
        
    else:
        # Plus then coalesce: pure additive calcs
        return TriccOperation(TriccOperator.COALESCE, [expression] + priors)
        

def load_calculate(
    node, processed_nodes, stashed_nodes, calculates, used_calculates, warn=False, process=None, **kwargs
):
    # used_calculates dict[name, Dict[id, node]]
    # processed_nodes Dict[id, node]
    # calculates  dict[name, Dict[id, node]]
    if isinstance(node, TriccGroup):
                return True
    if node not in processed_nodes:
        # generate condition
        if is_ready_to_process(node, processed_nodes, True) and process_reference(
            node,
            processed_nodes=processed_nodes,
            calculates=calculates,
            used_calculates=used_calculates,
            replace_reference=False,
            warn=warn,
            codesystems=kwargs.get("codesystems", None),
        ):
            if kwargs.get("warn", True):
                logger.debug("Processing relevance for node {0}".format(node.get_name()))
            # tricc diagnostic have the same name as proposed diag but will be serialised with different names

            set_last_version_false(node, processed_nodes)
            # Get all previous versions from processed_nodes, not just the last one
            node_name = node.name if not isinstance(node, TriccNodeEnd) else node.get_reference()
            from tricc_oo.models.base import get_repeat

            all_prev_versions = get_versions(node_name, processed_nodes, get_repeat(node))
            # Exclude the current node itself
            all_prev_versions = [v for v in all_prev_versions if v != node]

            if all_prev_versions:
                get_version_inheritance(node, all_prev_versions, processed_nodes)

            if isinstance(node, TriccNodePopulate):
                from tricc_oo.converters.fhir.populate_helper import resolve_populate_reference

                node.expression_reference = TriccStatic(resolve_populate_reference(node))
                node.is_sequence_defined = True

            generate_calculates(node, calculates, used_calculates, processed_nodes=processed_nodes, process=process)

            # if has prev, create condition
            if hasattr(node, "relevance") and (node.relevance is None or not isinstance(node.relevance, TriccOperation)):
                node.relevance = get_node_expressions(node, processed_nodes=processed_nodes, process=process)
                # manage not Available
                if isinstance(node, TriccNodeSelectNotAvailable):
                    # update the checkbox
                    if node.parent:
                        if len(node.prev_nodes) == 1:
                            prev = list(node.prev_nodes)[0]
                            if isinstance(prev, TriccNodeMoreInfo) and prev.parent.name == node.name:
                                prev.parent = node

                        # managing more info on NotAvaialbee
                        parent_empty = TriccOperation(TriccOperator.ISNULL, [node.parent])
                        node.relevance = and_join([node.parent.relevance, parent_empty])
                        node.required = parent_empty
                        node.constraint = parent_empty
                        node.constraint_message = "Cannot be selected with a value entered above"
                        # update the check box parent : create loop error
                        node.parent.required = None  # "${{{0}}}=''".format(node.name)
                    else:
                        logger.warning("not available node {} does't have a single parent".format(node.get_name()))
                elif isinstance(node.relevance, TriccOperation):
                    relevance_reference = list(node.relevance.get_references())
                    for r in relevance_reference:
                        if issubclass(r.__class__, (TriccNodeDisplayCalculateBase)):
                            add_used_calculate(node, r, calculates, used_calculates, processed_nodes)
            # add skip logic for display node ()
            # repeat=-1 is "local-only": each occurrence stands on its own and must not
            # be skip-suppressed because another repeat=-1 occurrence of the same
            # concept was already captured elsewhere (see docs/tricc-elements.md,
            # "Concept repeat").
            if all_prev_versions and hasattr(node, "relevance") and get_repeat(node) != -1:
                # search for same node in completly differnt activity
                from tricc_oo.converters.fhir.populate_helper import populate_participates_in_skip

                skip_prev_versions = [l for l in all_prev_versions if populate_participates_in_skip(l)]
                last_expressions_other_activity = [
                    (and_join([has_node_data_operation(l),TriccOperation(TriccOperator.ISTRUE,[l.activity.root])])) for l in skip_prev_versions if (
                        node.is_sequence_defined and
                        node.activity.base_instance != l.activity.base_instance
                    )
                ]
                # search for same some in the same activity (might require a warning)
                last_expression_same_activity = [
                    has_node_data_operation(l) for l in skip_prev_versions if (
                        node.is_sequence_defined and
                        node.activity == l.activity
                    )
                ]

                # we don't care about the same some in other activity isntance because this is managed on activity level
                last_version_relevance = [*last_expressions_other_activity, *last_expression_same_activity]
                if last_version_relevance:
                    version_relevance = or_join(last_version_relevance)
                else:
                    version_relevance = None

                if version_relevance:
                    if getattr(node, "relevance", None):
                        node.relevance = and_join([not_clean(version_relevance), node.relevance])

                    elif hasattr(node, "relevance"):
                        node.relevance = version_relevance
            

            if (
                not node.is_sequence_defined
                and issubclass(type(node), TriccNodeDisplayCalculateBase)
                and not isinstance(node, (TriccNodeRhombus, TriccNodeFactor))
                and node.prev_nodes
            ):
                if node.reference:
                    logger.critical(f"{node.get_name()} has both reference and prev_nodes")
                node.is_sequence_defined = True
            # if hasattr(node, 'next_nodes'):
            # node.next_nodes=reorder_node_list(node.next_nodes, node.group)
            process_reference(
                node,
                processed_nodes=processed_nodes,
                calculates=calculates,
                used_calculates=used_calculates,
                replace_reference=True,
                warn=warn,
                codesystems=kwargs.get("codesystems", None),
            )
            if isinstance(node, (TriccNodeMainStart, TriccNodeActivityStart)):
                process_reference(
                    node.activity,
                    processed_nodes=processed_nodes,
                    calculates=calculates,
                    used_calculates=used_calculates,
                    replace_reference=True,
                    warn=warn,
                    codesystems=kwargs.get("codesystems", None),
                )

            return True
    # not ready to process or already processed

    return False


def has_node_data_operation(node):
    return TriccOperation(TriccOperator.ISTRUE if node.get_datatype() == 'boolean' else TriccOperator.ISNOTNULL, [node])

def get_max_named_version(calculates, name):
    max = 0
    if name in calculates:
        for node in calculates[name].values():
            if node.version > max:
                max = node.version
    return max


def get_count_node(node):
    count_id = generate_id(f"count{node.id}")
    count_name = "cnt_" + count_id
    return TriccNodeCount(
        id=count_id,
        group=node.group,
        activity=node.activity,
        label="count: " + node.get_name(),
        name=count_name,
        path_len=node.path_len,
    )

# Function that inject a wait after path that will wait for the nodes

def get_activity_wait(prev_nodes, nodes_to_wait, next_nodes, replaced_node=None, edge_only=False, activity=None):

    if issubclass(nodes_to_wait.__class__, TriccBaseModel):
        nodes_to_wait = [nodes_to_wait]
    if issubclass(prev_nodes.__class__, TriccBaseModel):
        prev_nodes = set([prev_nodes])
    elif isinstance(prev_nodes, list):
        prev_nodes = set(prev_nodes)

    iterator = iter(prev_nodes)
    prev_node = next(iterator)
    path = prev_node if len(prev_nodes) == 1 else get_bridge_path(prev_nodes, activity)

    activity = activity or prev_node.activity
    calc_node = TriccNodeWait(
        id=generate_id(f"ar{''.join([x.id for x in nodes_to_wait])}{activity.id}"),
        reference=nodes_to_wait,
        activity=activity,
        group=activity,
        path=path,
    )

    # start the wait and the next_nodes from the prev_nodes
    # add the wait as dependency of the next_nodes

    # add edge between rhombus and node

    set_prev_next_node(path, calc_node, edge_only=edge_only, activity=activity)
    for next_node in next_nodes:
        # if prev != replaced_node and next_node != replaced_node :
        #    set_prev_next_node(prev,next_node,replaced_node)
        # if first:
        # first = False
        set_prev_next_node(calc_node, next_node, edge_only=edge_only, activity=activity)

    return calc_node


def get_bridge_path(prev_nodes, node=None, edge_only=False):
    iterator = iter(prev_nodes)
    p_p_node = next(iterator)
    if node is None:
        node = p_p_node
    calc_id = generate_id(f"br{''.join([x.id for x in prev_nodes])}{node.id}")
    calc_name = "path_" + calc_id
    data = {
        "id": calc_id,
        "group": node.group,
        "activity": node.activity,
        "label": "path: " + (node.get_name()),
        "name": calc_name,
        "path_len": node.path_len + 1 * (node == p_p_node),
    }

    if (
        len(prev_nodes) > 1
        and sum(
            [0 if issubclass(n.__class__, (TriccNodeDisplayCalculateBase, TriccNodeRhombus)) else 1 for n in prev_nodes]
        )
        > 0
    ):
        calc = TriccNodeDisplayBridge(**data)
    else:
        calc = TriccNodeBridge(**data)
    if node:
        priority = getattr(node, 'priority', None)
        if priority:
            calc.priority = priority
    
    return calc


def inject_bridge_path(node, nodes):

    prev_nodes = [
        nodes[n.source]
        for n in list(
            filter(
                lambda x: (x.target == node.id or x.target == node) and x.source in list(nodes.keys()),
                node.activity.edges,
            )
        )
    ]
    if prev_nodes:
        calc = get_bridge_path(prev_nodes, node, edge_only=True)

        for e in node.activity.edges:
            if e.target == node.id:
                # if e.source in node.activity.nodes and len(node.activity.nodes[e.source].next_nodes):
                #     set_prev_next_node(node.activity[e.source], node, edge_only=True, replaced_node=node)
                # else:
                e.target = calc.id

        # add edge between bridge and node
        set_prev_next_node(calc, node, edge_only=True, activity=node.activity)
        node.path_len += 1
        return calc


def inject_node_before(before, node, activity):
    before.group = activity
    before.activity = activity
    activity.nodes[before.id] = before
    nodes = activity.nodes
    prev_nodes = node.prev_nodes.union(
        set(
            nodes[n.source]
            for n in list(
                filter(lambda x: (x.target == node.id or x.target == node) and x.source in nodes, node.activity.edges)
            )
        )
    )
    edge_processed = False
    before.path_len = node.path_len
    for e in node.activity.edges:
        if e.target == node.id:
            e.target = before.id
    for p in prev_nodes:
        if node in p.next_nodes:
            p.next_nodes.remove(node)
            p.next_nodes.append(before)

    # add edge between bridge and node
    set_prev_next_node(before, node, edge_only=not edge_processed, activity=node.activity)
    node.path_len += 1


def generate_calculates(node, calculates, used_calculates, processed_nodes, process):
    list_calc = []
    count_node = None
    # add select calcualte
    if issubclass(node.__class__, TriccNodeCalculateBase):
        if isinstance(node, TriccNodeRhombus):
            if (
                (node.expression_reference is None or isinstance(node.expression_reference, TriccOperation))
                and isinstance(node.reference, list)
                and len(node.reference) == 1
                and issubclass(node.reference[0].__class__, TriccNodeSelect)
            ):

                count_node = get_count_node(node)
                list_calc.append(count_node)
                set_prev_next_node(node.reference[0], count_node)
                node.path_len += 1

                if isinstance(node.expression_reference, TriccOperation):
                    node.expression_reference.replace_node(node.reference, count_node)
                node.reference[0] = count_node
            # elif isinstance(node.reference, TriccOperation):
            #     references = node.reference.get_references()
            #     if len(references) == 1 and issubclass(node.reference[0].__class__, TriccNodeSelect):
            #         count_node = get_count_node(node)
            #         list_calc.append(count_node)
            #         set_prev_next_node(references[0],count_node)
            #         node.path_len+=1
            #         node.reference.replace_node(references[0], count_node)
            if count_node:
                processed_nodes.add(count_node)
                add_calculate(calculates, count_node)
                add_used_calculate(
                    node,
                    count_node,
                    calculates=calculates,
                    used_calculates=used_calculates,
                    processed_nodes=processed_nodes,
                )

    # if a prev node is a calculate then it must be added in used_calc
    for prev in node.prev_nodes:
        add_used_calculate(
            node, prev, calculates=calculates, used_calculates=used_calculates, processed_nodes=processed_nodes
        )
    # if the node have a save
    if hasattr(node, "save") and node.save is not None and node.save != "":
        # get fragments type.name.icdcode
        calculate_name = node.save
        if node.name != calculate_name:
            calc_id = generate_id(f"autosave{node.id}")
            if issubclass(node.__class__, TriccNodeSelect) or isinstance(node, TriccNodeSelectNotAvailable):
                expression = get_count_terms_details(node, processed_nodes, True, False, process)
            else:
                expression = get_node_expression(node, processed_nodes, True, True)
            calc_node = TriccNodeCalculate(
                name=calculate_name,
                id=calc_id,
                group=node.group,
                # version=get_next_version(calculate_name, processed_nodes, node.version+2),
                activity=node.activity,
                label="save: " + node.get_name(),
                path_len=node.path_len + 1,
                last=True,
                expression=expression,
            )
            node.activity.calculates.append(calc_node)
            last_version = set_last_version_false(calc_node, processed_nodes)
            if last_version:
                calc_node.expression = merge_expressions(calc_node.expression, last_version)
            processed_nodes.add(calc_node)
            # logger.debug(
            #     "generate_save_calculate:{}:{} as {}".format(
            #         calc_node.tricc_type, node.name if hasattr(node, "name") else node.id, calculate_name
            #     )
            # )

            list_calc.append(calc_node)
            # add_save_calculate(calc_node, calculates, used_calculates,processed_nodes)
            for calc in list_calc:
                node.activity.nodes[calc.id] = calc
                add_calculate(calculates, calc)

    # Add CONTAINS calculations for each option in select multiple (except opt_none)
    if isinstance(node, TriccNodeSelectMultiple):
        for option in node.options.values():
            if not option.name.startswith("opt_") and node.name != 'manual.diag':
                calc_id = generate_id(f"contains_{node.id}_{option.name}")
                expression = TriccOperation(TriccOperator.CONTAINS, [node, option.name])
                calc_node = TriccNodeCalculate(
                    name=option.name,
                    id=calc_id,
                    group=node.group,
                    activity=node.activity,
                    label=f"contains: {node.get_name()} contains '{option.name}'",
                    path_len=node.path_len + 1,
                    last=True,
                    expression=expression,
                )
                node.activity.calculates.append(calc_node)
                last_version = set_last_version_false(calc_node, processed_nodes)
                if last_version:
                    calc_node.expression = merge_expressions(calc_node.expression, last_version)
                processed_nodes.add(calc_node)
                list_calc.append(calc_node)
                node.activity.nodes[calc_node.id] = calc_node
                add_calculate(calculates, calc_node)

    return list_calc


def add_calculate(calculates, calc_node):
    if issubclass(calc_node.__class__, TriccNodeDisplayCalculateBase):
        if calc_node.name not in calculates:
            calculates[calc_node.name] = {}
        calculates[calc_node.name][calc_node.id] = calc_node


def get_option_code_from_label(node, option_label):
    if hasattr(node, "options"):
        for i in node.options:
            if node.options[i].label.strip() == option_label.strip():
                return node.options[i].name
        logger.critical(f"option with label {option_label} not found in {node.get_name()}")
    else:
        logger.critical(f"node {node.get_name()} has no options")


# CQL is deined as a cql library and this code will
# parse the definition and will extract the logic under the define statement


def extract_with_regex(data):
    text = data
    # Pattern to match define statement and capture the name and body
    pattern = r'define\s+"([^"]+)":\s*(.*)'
    match = re.search(pattern, text, re.DOTALL)

    if match:
        definition_name = match.group(1)
        definition_body = match.group(2).strip()
        return {"name": definition_name, "body": definition_body, "full": match.group(0)}
    return None


def process_reference(
    node, processed_nodes, calculates, used_calculates=None, replace_reference=False, warn=False, codesystems=None
):
    # process a remote reference coded as a cql
    if getattr(node, "remote_reference", None):
        remote_reference_url = node.remote_reference
        print(f"Fetching remote reference from {remote_reference_url}")
        response = requests.get(remote_reference_url)
        response_json = response.json()
        cql_content = response_json["content"][0]["data"]
        decode_cql_content = base64.b64decode(cql_content).decode("utf-8")
        definition = extract_with_regex(decode_cql_content)

        if definition:
            cql_expression = definition["body"]

            # We use `transform_cql_to_operation` to parse the raw CQL string.
            operation = transform_cql_to_operation(cql_expression, context=f"remote reference for {node.get_name()}")

            if not operation:
                logger.error(f"Failed to parse remote CQL expression for node {node.get_name()}: {cql_expression}")
                return False

            # The parsed operation is assigned to `expression_reference`.
            # The original code incorrectly assigned the raw string to `node.reference`
            # and had an unreachable `if isinstance(cql_expression, list):` block.
            node.expression_reference = operation
            node.remote_reference = None

            # By setting `expression_reference` and clearing `remote_reference`,
            # we can now re-process this node. A recursive call to `process_reference`
            # will now enter the `elif getattr(node, 'expression_reference', None):`
            # block, which will correctly handle the newly parsed expression.
            return process_reference(
                node, processed_nodes, calculates, used_calculates, replace_reference, warn, codesystems
            )

    elif getattr(node, "expression_reference", None):
        modified_expression = process_operation_reference(
            node.expression_reference,
            node,
            processed_nodes=processed_nodes,
            calculates=calculates,
            used_calculates=used_calculates,
            replace_reference=replace_reference,
            warn=warn,
            codesystems=codesystems,
            inherit_display_versions=True,
        )
        if modified_expression is False:
            return False
        elif modified_expression and replace_reference:
            node.reference = list(modified_expression.get_references())
            node.expression_reference = modified_expression

    elif getattr(node, "reference", None):
        reference = node.reference
        if isinstance(reference, list):
            if isinstance(node, TriccNodeWait):
                reference = [TriccOperation(TriccOperator.ISTRUE, [n]) for n in reference]
            if len(node.reference) == 1:
                operation = reference[0]
            else:
                operation = and_join(reference)
            modified_expression = process_operation_reference(
                operation,
                node,
                processed_nodes=processed_nodes,
                calculates=calculates,
                used_calculates=used_calculates,
                replace_reference=replace_reference,
                warn=warn,
                codesystems=codesystems,
                inherit_display_versions=True,
            )
            if modified_expression is False:
                return False
            elif modified_expression:
                node.reference = list(modified_expression.get_references())
                if not isinstance(node, TriccNodeWait):
                    node.expression_reference = modified_expression
        elif isinstance(node.reference, (TriccOperation, TriccReference)):
            modified_expression = process_operation_reference(
                node.reference,
                node,
                processed_nodes=processed_nodes,
                calculates=calculates,
                used_calculates=used_calculates,
                replace_reference=replace_reference,
                warn=warn,
                codesystems=codesystems,
                inherit_display_versions=True,
            )
            if modified_expression is False:
                return False
            elif modified_expression and replace_reference:
                node.reference = list(modified_expression.get_references())
                node.expression_reference = modified_expression

    if isinstance(getattr(node, "relevance", None), (TriccOperation, TriccReference)):
        modified_expression = process_operation_reference(
            node.relevance,
            node,
            processed_nodes=processed_nodes,
            calculates=calculates,
            used_calculates=used_calculates,
            replace_reference=replace_reference,
            warn=warn,
            codesystems=codesystems,
            inherit_display_versions=False,
        )
        if modified_expression is False:
            return False
        elif modified_expression and replace_reference:
            node.relevance = modified_expression

    if isinstance(getattr(node, "trigger", None), (TriccOperation, TriccReference)):
        modified_expression = process_operation_reference(
            node.trigger,
            node,
            processed_nodes=processed_nodes,
            calculates=calculates,
            used_calculates=used_calculates,
            replace_reference=replace_reference,
            warn=warn,
            codesystems=codesystems,
            inherit_display_versions=False,
        )
        if modified_expression is False:
            return False
        elif modified_expression and replace_reference:
            node.trigger = modified_expression
    if isinstance(getattr(node, "constraint", None), (TriccOperation, TriccReference)):
        modified_expression = process_operation_reference(
            node.constraint,
            node,
            processed_nodes=processed_nodes,
            calculates=calculates,
            used_calculates=used_calculates,
            replace_reference=replace_reference,
            warn=warn,
            codesystems=codesystems,
            inherit_display_versions=False,
        )
        if modified_expression is False:
            return False
        elif modified_expression and replace_reference:
            node.constraint = modified_expression

    if isinstance(getattr(node, "default", None), (TriccOperation, TriccReference)):
        modified_expression = process_operation_reference(
            node.default,
            node,
            processed_nodes=processed_nodes,
            calculates=calculates,
            used_calculates=used_calculates,
            replace_reference=replace_reference,
            warn=warn,
            codesystems=codesystems,
            inherit_display_versions=False,
        )
        if modified_expression is False:
            return False
        elif modified_expression and replace_reference:
            node.relevance = modified_expression

    if isinstance(getattr(node, "expression", None), (TriccOperation, TriccReference)):
        modified_expression = process_operation_reference(
            node.expression,
            node,
            processed_nodes=processed_nodes,
            calculates=calculates,
            used_calculates=used_calculates,
            replace_reference=replace_reference,
            warn=warn,
            codesystems=codesystems,
            inherit_display_versions=True,
        )
        if modified_expression is False:
            return False
        elif modified_expression and replace_reference:
            node.expression = modified_expression

    if isinstance(getattr(node, "applicability", None), (TriccOperation, TriccReference)):
        modified_expression = process_operation_reference(
            node.applicability,
            node,
            processed_nodes=processed_nodes,
            calculates=calculates,
            used_calculates=used_calculates,
            replace_reference=replace_reference,
            warn=warn,
            codesystems=codesystems,
            inherit_display_versions=False,
        )
        if modified_expression is False:
            return False
        elif modified_expression and replace_reference:
            node.applicability = modified_expression

    # Display-model only: resolve ${REF} injection ops already parsed at input load
    if isinstance(node, TriccNodeDisplayModel):

        for field in TEXT_INJECTION_FIELDS:
            if not hasattr(node, field):
                continue
            value = getattr(node, field, None)
            if value is None:
                continue
            if isinstance(value, dict):
                new_dict = {}
                changed = False
                for locale, entry in value.items():
                    if isinstance(entry, (TriccOperation)):
                        modified = process_operation_reference(
                            entry,
                            node,
                            processed_nodes=processed_nodes,
                            calculates=calculates,
                            used_calculates=used_calculates,
                            replace_reference=replace_reference,
                            warn=warn,
                            codesystems=codesystems,
                        )
                        if modified is False:
                            return False
                        if modified and replace_reference:
                            new_dict[locale] = modified
                            changed = True
                        else:
                            new_dict[locale] = entry
                    else:
                        new_dict[locale] = entry
                if changed and replace_reference:
                    setattr(node, field, new_dict)
            elif isinstance(value, (TriccOperation)):
                modified_expression = process_operation_reference(
                    value,
                    node,
                    processed_nodes=processed_nodes,
                    calculates=calculates,
                    used_calculates=used_calculates,
                    replace_reference=replace_reference,
                    warn=warn,
                    codesystems=codesystems,
                )
                if modified_expression is False:
                    return False
                elif modified_expression and replace_reference:
                    setattr(node, field, modified_expression)
    return True


def get_repeat_index_arg(operation) -> Optional[int]:
    """Extract the repeat-slot literal of a ``GET_REPEATED_VALUE`` operation.

    ``GET_REPEATED_VALUE(<concept reference>, <slot literal>)`` consumes its second
    operand while resolving the first: the slot pins which capture node the reference
    may bind to (see ``feature/20260821-get-repeated-value-operation.md``).

    Args:
        operation: The ``TriccOperation`` carrying the slot as its second reference.

    Returns:
        The slot as an int; ``1`` when the argument is missing (default capture slot);
        ``None`` when it is not a literal integer, which leaves the reference
        unscoped rather than failing the whole conversion.
    """
    references = list(getattr(operation, "reference", None) or [])
    if len(references) < 2:
        logger.warning(
            "GetRepeatedValue without a repeat slot argument; defaulting to slot 1"
        )
        return 1
    raw = references[1]
    value = raw.value if isinstance(raw, TriccStatic) else raw
    try:
        return int(value)
    except (TypeError, ValueError):
        logger.warning(
            f"GetRepeatedValue repeat slot {value!r} is not an integer literal; "
            "resolving the reference across all slots"
        )
        return None


def resolve_slot_scoped_children(
    operation,
    node,
    processed_nodes,
    calculates=None,
    used_calculates=None,
    replace_reference=False,
    warn=False,
    codesystems=None,
    inherit_display_versions=False,
):
    """Resolve ``GET_REPEATED_VALUE`` sub-operations against their own repeat slot.

    ``process_operation_reference`` resolves a name once for the whole expression, so
    ``GetRepeatedValue("weight", 2) - GetRepeatedValue("weight", 1)`` would bind both
    occurrences to the same node (``replace_node`` rewrites the entire tree). Each
    slot-scoped child is therefore resolved on its own subtree — where it *is* the
    top-level operator, so the slot argument applies — and spliced back in place.

    Args:
        operation: Operation whose subtree may contain slot-scoped children.
        node: Node the expression belongs to (path_len / used-calculate bookkeeping).
        processed_nodes: Nodes already processed, used for version lookup.

    Returns:
        A modified copy of *operation* when a child was resolved, ``None`` when there was
        nothing to resolve, or ``False`` when a child cannot be resolved yet (defer).
    """
    if not isinstance(operation, TriccOperation):
        return None
    if not any(isinstance(r, TriccOperation) for r in (operation.reference or [])):
        return None  # no sub-operations: nothing this pass can own

    deferred = False

    def _has_unresolved(op):
        return any(isinstance(r, TriccReference) for r in (op.get_references() or []))

    def _walk(container):
        """Splice resolved slot-scoped children into *container*; return True if changed.

        Deferral is reported through the ``deferred`` flag, never the return value — a
        falsy return only ever means "nothing to change here".
        """
        nonlocal deferred
        changed = False
        for index, item in enumerate(container):
            if deferred:
                return changed
            if isinstance(item, list):
                changed = _walk(item) or changed
                continue
            if not isinstance(item, TriccOperation):
                continue
            if item.operator == TriccOperator.GET_REPEATED_VALUE and _has_unresolved(item):
                resolved = process_operation_reference(
                    item,
                    node,
                    processed_nodes,
                    calculates=calculates,
                    used_calculates=used_calculates,
                    replace_reference=replace_reference,
                    warn=warn,
                    codesystems=codesystems,
                    inherit_display_versions=inherit_display_versions,
                )
                if resolved is False:
                    deferred = True
                    return changed
                if resolved is not None:
                    container[index] = resolved
                    changed = True
                continue
            changed = _walk(item.reference) or changed
        return changed

    candidate = operation.copy(keep_node=True)
    changed = _walk(candidate.reference)
    if deferred:
        return False
    return candidate if changed else None


def process_operation_reference(
    operation,
    node,
    processed_nodes,
    calculates=None,
    used_calculates=None,
    replace_reference=False,
    warn=False,
    codesystems=None,
    inherit_display_versions=False,
):
    """
    Process references inside an operation expression.

    Args:
        inherit_display_versions: When True (expression / expression_reference only),
            multi-version TriccNodeDisplayModel refs become GET_INHERITED_VALUE of all
            versions. Must stay False for relevance and other non-value fields.

    Returns:
        - modified_operation (or None if no replacement occurred)
        - False if processing should be deferred (unresolved references)
    """
    if not operation or not hasattr(operation, 'get_references') or not operation.get_references():
        return None  # nothing to do

    modified_op = None
    resolved_nodes = []           # TriccNodeBaseModel instances
    resolved_refs = []            # TriccReference objects kept for compatibility
    unresolved_names = []         # strings that are still not resolved

    # ───────────────────────────────────────────────
    # 0. Slot-scoped sub-operations first
    # ───────────────────────────────────────────────
    # GET_REPEATED_VALUE names one repeat slot, but the flat pass below resolves every
    # occurrence of a name identically (replace_node rewrites the whole tree). So each
    # GetRepeatedValue(<concept>, <slot>) child is resolved in its own scope, before its
    # reference can be caught by the flat pass.
    prepass = resolve_slot_scoped_children(
        operation,
        node,
        processed_nodes,
        calculates=calculates,
        used_calculates=used_calculates,
        replace_reference=replace_reference,
        warn=warn,
        codesystems=codesystems,
        inherit_display_versions=inherit_display_versions,
    )
    if prepass is False:
        return False
    if prepass is not None:
        modified_op = prepass
    source_op = modified_op if modified_op is not None else operation

    # ───────────────────────────────────────────────
    # 1. Collect all reference strings and classify them
    # ───────────────────────────────────────────────
    string_refs = [r.value for r in source_op.get_references() if isinstance(r, TriccReference)]
    real_node_refs = [r for r in source_op.get_references() if issubclass(r.__class__, TriccNodeBaseModel)]

    # Repeat slot the whole operation is scoped to, when the operator selects one.
    # GET_HISTORY_VALUE reads outside the encounter slots; GET_REPEATED_VALUE names a slot.
    if source_op.operator == TriccOperator.GET_HISTORY_VALUE:
        op_repeat = 0
    elif source_op.operator == TriccOperator.GET_REPEATED_VALUE:
        op_repeat = get_repeat_index_arg(source_op)
    else:
        op_repeat = None

    for ref_str in string_refs:
        option_label = None
        clean_ref = ref_str

        # Handle option syntax: question[option_label]
        if ref_str.endswith("]"):
            parts = ref_str[:-1].split("[", 1)
            if len(parts) == 2:
                clean_ref, option_label = parts

        # Try to find the referenced node
        from tricc_oo.models.base import get_repeat

        ref_repeat = op_repeat  # TODO: manage repeat in scv get_repeat(node)
        # Same-name nodes in the activity (common after snippet inject of a module
        # multiple times). Do NOT require every candidate to be processed — later
        # injects are not yet processed when earlier calculates resolve, and that
        # deadlocks load_calculate / blocks set_last_version_false.
        candidates_in_activity = [
            n for n in node.activity.nodes.values()
            if getattr(n, "name", None) == clean_ref
            and n != node
            and not isinstance(n, TriccNodeSelectOption)
            and (ref_repeat is None or get_repeat(n) == ref_repeat)
        ]
        processed_candidates = [n for n in candidates_in_activity if n in processed_nodes]

        if candidates_in_activity:
            if not processed_candidates:
                return False  # nothing ready yet for this name
            # Prefer the most advanced processed version (path then version)
            target_node = sorted(
                processed_candidates,
                key=lambda n: (
                    getattr(n, "path_len", 0) or 0,
                    getattr(n, "version", 0) or 0,
                    str(getattr(n, "id", "")),
                ),
            )[-1]
        else:
            target_node = get_last_version(
                name=clean_ref, processed_nodes=processed_nodes, repeat=ref_repeat
            )

        if target_node is None or isinstance(target_node, TriccNodeSelectOption):
            unresolved_names.append(ref_str)  # keep original form with [label] if present
            continue

        # We found a valid node
        resolved_nodes.append(target_node)
        resolved_refs.append(TriccReference(clean_ref))

        # Option syntax handling
        if option_label:
            option_code = get_option_code_from_label(target_node, option_label)
            if option_code:
                # Replace the full "q[opt]" → option code
                if modified_op is None:
                    modified_op = operation.copy(keep_node=True)
                modified_op = replace_code_reference(
                    modified_op,
                    old=f"{clean_ref}[{option_label}]",
                    new=option_code
                )
            else:
                if warn:
                    logger.warning(f"Cannot resolve option label '{option_label}' in {clean_ref!r} for {node}")
                return False

        # Replace node reference in expression if requested
        if replace_reference:
            replacement = target_node
            # Expression / expression_reference only: multi-version display fields
            # need GET_INHERITED_VALUE so ODK coalesce picks whichever instance was
            # filled. Relevance and other fields must keep a single last version.
            if inherit_display_versions:
                last_version = get_last_version(
                    name=clean_ref, processed_nodes=processed_nodes, repeat=ref_repeat
                ) or target_node
                if (
                    issubclass(last_version.__class__, TriccNodeDisplayModel)
                    and not isinstance(last_version, TriccNodeSelectOption)
                    and get_repeat(last_version) != -1
                ):
                    # repeat=-1 stays referenceable as a single node, but is never
                    # merged into GET_INHERITED_VALUE multi-version coalesce.
                    all_versions = [
                        n
                        for n in get_versions(clean_ref, processed_nodes, ref_repeat)
                        if issubclass(n.__class__, TriccNodeDisplayModel)
                        and not isinstance(n, TriccNodeSelectOption)
                        and get_repeat(n) != -1
                    ]
                    if not all_versions:
                        all_versions = [last_version]
                    if len(all_versions) > 1:
                        # coalesce is left-to-right: prefer newer versions first
                        ordered = sorted(
                            all_versions,
                            key=lambda n: (
                                getattr(n, "path_len", 0) or 0,
                                getattr(n, "version", 0) or 0,
                            ),
                            reverse=True,
                        )
                        replacement = TriccOperation(
                            TriccOperator.GET_INHERITED_VALUE, ordered
                        )
                    else:
                        replacement = all_versions[0]
            if (
                replacement is target_node
                and not issubclass(
                    target_node.__class__,
                    (
                        TriccNodeDisplayModel,
                        TriccNodeDisplayCalculateBase,
                        TriccNodePopulate,
                    ),
                )
            ):
                replacement = get_node_expression(target_node, processed_nodes, is_prev=True)

            if modified_op is None:
                modified_op = operation.copy(keep_node=True)

            if isinstance(operation, TriccOperation):
                modified_op.replace_node(TriccReference(clean_ref), replacement)
            elif operation == TriccReference(clean_ref):
                modified_op = replacement

            target_node = replacement

        # Update path length
        path_len = getattr(target_node, "path_len", 0)
        if isinstance(target_node, TriccOperation):
            refs = target_node.get_references() or []
            path_len = max((getattr(n, "path_len", 0) or 0) for n in refs) if refs else 0
        node.path_len = max(node.path_len, path_len or 0)

    # ───────────────────────────────────────────────
    # 2. Check real node references (already objects)
    # ───────────────────────────────────────────────
    for ref_node in real_node_refs:
        if not is_prev_processed(ref_node, node, processed_nodes=processed_nodes, local=False):
            return False

    # ───────────────────────────────────────────────
    # 3. Try to resolve remaining unfound names → maybe they are options
    # ───────────────────────────────────────────────
    still_unresolved = []

    for orig_ref in unresolved_names:
        found = False

        # Check if it's an option of an already resolved select question
        for sel_node in [*real_node_refs, *resolved_nodes]:
            if not issubclass(sel_node.__class__, TriccNodeSelect):
                continue

            for opt in sel_node.options.values():
                if opt.name == orig_ref:
                    resolved_nodes.append(opt)
                    resolved_refs.append(TriccReference(opt.name))
                    found = True

                    # Important: also inject into modified operation!
                    if modified_op is None:
                        modified_op = operation.copy(keep_node=True)
                    modified_op.replace_node(TriccReference(orig_ref), opt)

                    break

            if found:
                break

        if not found:
            still_unresolved.append(orig_ref)

    # ───────────────────────────────────────────────
    # 4. Handle still unresolved references
    # ───────────────────────────────────────────────
    if still_unresolved:
        for ref in still_unresolved:
            if codesystems:
                concept = lookup_codesystems_code(codesystems, ref)
                if concept:
                    if warn:
                        logger.debug(f"Code system ref {ref} → {concept.display} (not processed yet?)")
                    return False
                else:
                    logger.critical(f"Reference not found in codesystems: {ref} in {node}")
                    exit(1)
            else:
                if warn:
                    slot = f" (repeat slot {op_repeat})" if op_repeat is not None else ""
                    logger.debug(
                        f"Unresolved reference {ref!r}{slot} in calculate/display {node.get_name()}"
                    )
                return False

    # ───────────────────────────────────────────────
    # 5. Register used calculates if requested
    # ───────────────────────────────────────────────
    if used_calculates is not None:
        for n in resolved_nodes:
            if issubclass(n.__class__, TriccNodeCalculateBase):
                add_used_calculate(
                    node,
                    n,
                    calculates,
                    used_calculates,
                    processed_nodes=processed_nodes
                )

    return modified_op


def replace_code_reference(expression, old, new):
    if isinstance(expression, str):
        return expression.replace(old, f"'{new}'")
    if isinstance(expression, TriccOperation):
        expression.replace_node(TriccReference(old), TriccStatic(new))
        return expression


# add_used_calculate(node, calc_node, calculates, used_calculates, processed_nodes)


def add_used_calculate(node, prev_node, calculates, used_calculates, processed_nodes):
    if issubclass(prev_node.__class__, TriccNodeDisplayCalculateBase):
        if prev_node in processed_nodes:
            # if not a verison, index will equal -1
            if prev_node.name not in calculates:
                #logger.debug("node {} refered before being processed".format(node.get_name()))
                return False
            max_version = prev_node  # get_max_version(calculates[node_clean_name])
            if prev_node.name not in used_calculates:
                used_calculates[prev_node.name] = {}
            # save the max version only once
            if max_version.id not in used_calculates[prev_node.name]:
                used_calculates[prev_node.name][max_version.id] = max_version
        else:
            logger.debug(
                "load_calculate_version_requirement: failed for {0} , prev Node {1} ".format(
                    node.get_name(), prev_node.get_name()
                )
            )


def get_select_not_available_options(node, group, label):
    return {
        0: TriccNodeSelectOption(
            id=generate_id(f"notavaialble{node.id}"),
            name="1",
            label=label,
            select=node,
            group=group,
            list_name=node.list_name,
        )
    }


def get_select_yes_no_options(node, group):
    yes = TriccNodeSelectOption(
        id=generate_id(f"yes{node.id}"),
        name=f"{TRICC_TRUE_VALUE}",
        label="Yes",
        select=node,
        group=group,
        list_name=node.list_name,
    )
    no = TriccNodeSelectOption(
        id=generate_id(f"no{node.id}"),
        name=f"{TRICC_FALSE_VALUE}",
        label="No",
        select=node,
        group=group,
        list_name=node.list_name,
    )
    return {0: yes, 1: no}


# walkthough all node in an iterative way, the same node might be parsed 2 times
# therefore to avoid double processing the nodes variable saves the node already processed
# there 2 strategies : process it the first time or the last time (wait that all the previuous node are processed)


def stash_next_nodes(stashed_nodes, next_nodes):
    """Push successors so the first next-node is processed first.

    ``insert_at_top`` plus ``pop()`` from the front is a stack. Inserting in
    authored order would reverse siblings (last edge first). Insert reversed
    so the first edge sits at the front of the stash.
    See fix/20260823-questionnaire-item-order.md.
    """
    if not next_nodes:
        return
    for nn in reversed(list(next_nodes)):
        if nn not in stashed_nodes:
            stashed_nodes.insert_at_top(nn)


def walktrhough_tricc_node_processed_stached(
    node,
    callback,
    processed_nodes,
    stashed_nodes,
    path_len,
    recursive=False,
    warn=False,
    node_path=[],
    process=None,
    loop_count=0,
    **kwargs,
):
    # logger.debug("walkthrough::{}::{}".format(callback.__name__, node.get_name()))
    priority_map = kwargs.get('priority_map', {})
    path_len = max(node.activity.path_len, *[0, *[getattr(n, "path_len", 0) + 1 for n in node.activity.prev_nodes]]) + 1
    if hasattr(node, "prev_nodes"):
        path_len = max(path_len, *[0, *[getattr(n, "path_len", 0) + 1 for n in node.prev_nodes]])
    if hasattr(node, "get_references"):
        references = node.get_references()
        if references:
            path_len = max(path_len, *[0, *[getattr(n, "path_len", 0) + 1 for n in references]])
    node.path_len = max(node.path_len, path_len)
    prev_process = process[0] if process else None
    if isinstance(node, TriccNodeActivity) and getattr(node.root, "process", None):
        if process is None:
            process = [node.root.process]
        else:
            process[0] = node.root.process
    if callback(
        node,
        processed_nodes=processed_nodes,
        stashed_nodes=stashed_nodes,
        warn=warn,
        node_path=node_path,
        process=process,
        **kwargs,
    ):
        node_path.append(node)
        # node processing succeed
        if not isinstance(node, TriccNodeActivity) and node not in processed_nodes:
            processed_nodes.add(node)
            if warn:
                logger.debug("{}::{}: processed ({})".format(callback.__name__, node.get_name(), len(processed_nodes)))
        if isinstance(node, (TriccNodeEnd, TriccNodeActivityEnd)) and node.activity not in processed_nodes:
            end_nodes = node.activity.get_end_nodes()
            if all([e in processed_nodes for e in end_nodes]):
                processed_nodes.add(node.activity)
                if warn:
                    logger.debug(
                        "{}::{}: processed ({})".format(
                            callback.__name__, node.activity.get_name(), len(processed_nodes)
                        )
                    )
                # the activity is fully processed: schedule whatever comes directly after it
                # (nodes wired as next_nodes of the TriccNodeActivity itself, e.g. when a repeated
                # instance has no bridge/wait in between) - the activity is never revisited on its
                # own once it defers to its root, so this is the only place this can happen.
                if recursive:
                    for next_node in node.activity.next_nodes:
                        if next_node not in processed_nodes:
                            walktrhough_tricc_node_processed_stached(
                                next_node,
                                callback,
                                processed_nodes,
                                stashed_nodes,
                                path_len,
                                recursive,
                                warn=warn,
                                node_path=node_path.copy(),
                                **kwargs,
                            )
                else:
                    stash_next_nodes(stashed_nodes, node.activity.next_nodes)
        elif node in stashed_nodes:
            stashed_nodes.remove(node)
            # logger.debug("{}::{}: unstashed ({})".format(callback.__name__, node.get_name(), len(stashed_nodes)))
        # put the stached node from that group first
        # if has next, walkthrough them (support options)
        # if len(stashed_nodes)>1:
        if isinstance(node, (TriccNodeActivityStart, TriccNodeMainStart)):
            if recursive:
                for gp in node.activity.groups.values():
                    walktrhough_tricc_node_processed_stached(
                        gp,
                        callback,
                        processed_nodes=processed_nodes,
                        stashed_nodes=stashed_nodes,
                        path_len=path_len,
                        recursive=recursive,
                        warn=warn,
                        node_path=node_path.copy(),
                        **kwargs,
                    )
                for c in node.activity.calculates:
                    if len(c.prev_nodes) == 0:
                        walktrhough_tricc_node_processed_stached(
                            c,
                            callback,
                            processed_nodes=processed_nodes,
                            stashed_nodes=stashed_nodes,
                            path_len=path_len,
                            recursive=recursive,
                            warn=warn,
                            node_path=node_path.copy(),
                            **kwargs,
                        )
            else:
                stashed_nodes += [c for c in node.activity.calculates if len(c.prev_nodes) == 0]
                stashed_nodes += node.activity.groups.values()
        elif issubclass(node.__class__, TriccNodeSelect):
            for option in node.options.values():
                option.path_len = max(path_len, option.path_len)
                callback(
                    option,
                    processed_nodes=processed_nodes,
                    stashed_nodes=stashed_nodes,
                    warn=warn,
                    node_path=node_path,
                    **kwargs,
                )
                if option not in processed_nodes:
                    processed_nodes.add(option)
                    if warn:
                        logger.debug(
                            "{}::{}: processed ({})".format(callback.__name__, option.get_name(), len(processed_nodes))
                        )
                walkthrough_tricc_option(
                    node,
                    callback,
                    processed_nodes,
                    stashed_nodes,
                    path_len + 1,
                    recursive,
                    warn=warn,
                    node_path=node_path,
                    **kwargs,
                )
        if isinstance(node, TriccNodeActivity):
            if node.root not in processed_nodes:
                if node.root is not None:
                    node.root.path_len = max(path_len, node.root.path_len)
                    if recursive:
                        walktrhough_tricc_node_processed_stached(
                            node.root,
                            callback,
                            processed_nodes,
                            stashed_nodes,
                            path_len,
                            recursive,
                            warn=warn,
                            node_path=node_path.copy(),
                            **kwargs,
                        )
                    elif node.root not in stashed_nodes:
                        stash_next_nodes(stashed_nodes, [node.root])
                    return

        elif hasattr(node, "next_nodes") and len(node.next_nodes) > 0 and not isinstance(node, TriccNodeActivity):
            if recursive:
                walkthrough_tricc_next_nodes(
                    node,
                    callback,
                    processed_nodes,
                    stashed_nodes,
                    path_len + 1,
                    recursive,
                    warn=warn,
                    node_path=node_path,
                    **kwargs,
                )
            else:
                stash_next_nodes(stashed_nodes, node.next_nodes)
        if not recursive:
            #global _last_reordered_group
            #if _last_reordered_group != node.group:
                reorder_node_list(stashed_nodes, node.group, processed_nodes, priority_map)
            #    _last_reordered_group = n  ode.group

    else:
        if prev_process and process and prev_process != process[0]:
            process[0] = prev_process
        if node not in processed_nodes and node not in stashed_nodes:
            if node not in stashed_nodes:
                stashed_nodes.insert_at_bottom(node)
                if warn:
                    logger.debug("{}::{}: stashed({})".format(callback.__name__, node.get_name(), len(stashed_nodes)))


def walkthrough_tricc_next_nodes(
    node, callback, processed_nodes, stashed_nodes, path_len, recursive, warn=False, node_path=[], **kwargs
):

    if not recursive:
        stash_next_nodes(stashed_nodes, node.next_nodes)
    else:
        list_next = set(node.next_nodes)
        for next_node in list_next:
            if not isinstance(node, (TriccNodeActivityEnd, TriccNodeEnd)):
                if next_node not in processed_nodes:
                    walktrhough_tricc_node_processed_stached(
                        next_node,
                        callback,
                        processed_nodes,
                        stashed_nodes,
                        path_len + 1,
                        recursive,
                        warn=warn,
                        node_path=node_path.copy(),
                        **kwargs,
                    )
            else:
                logger.critical(
                    "{}::end node of {} has a next node".format(callback.__name__, node.activity.get_name())
                )
                exit(1)


def walkthrough_tricc_option(
    node, callback, processed_nodes, stashed_nodes, path_len, recursive, warn=False, node_path=[], **kwargs
):
    if not recursive:
        for option in reversed(list(node.options.values())):
            if hasattr(option, "next_nodes") and len(option.next_nodes) > 0:
                stash_next_nodes(stashed_nodes, option.next_nodes)
    else:
        list_option = []
        while not all(elem in list_option for elem in list(node.options.values())):
            for option in node.options.values():
                if option not in list_option:
                    list_option.append(option)
                    # then walk the options
                    if hasattr(option, "next_nodes") and len(option.next_nodes) > 0:
                        list_next = set(option.next_nodes)
                        for next_node in list_next:
                            if next_node not in processed_nodes:
                                walktrhough_tricc_node_processed_stached(
                                    next_node,
                                    callback,
                                    processed_nodes,
                                    stashed_nodes,
                                    path_len + 1,
                                    recursive,
                                    warn=warn,
                                    node_path=node_path.copy(),
                                    **kwargs,
                                )


def get_next_version(name, processed_nodes, version=0, min=100, repeat=None):
    return (
        max(
            version,
            min,
            *[
                (getattr(n, "version", None) or getattr(n, "instance", None) or 0)
                for n in get_versions(name, processed_nodes, repeat)
            ],
        )
        + 1
    )


def get_data_for_log(node):
    return "{}:{}|{} {}:{}".format(
        node.group.get_name() if node.group is not None else node.activity.get_name(),
        node.group.instance if node.group is not None else node.activity.instance,
        node.__class__,
        node.get_name(),
        node.instance,
    )


def stashed_node_func(node, callback, recursive=False, **kwargs):
    processed_nodes = kwargs.pop("processed_nodes", OrderedSet())
    stashed_nodes = kwargs.pop("stashed_nodes", OrderedSet())
    process = kwargs.pop("process", ["main"])
    path_len = 0
    priority_map = {}
    walktrhough_tricc_node_processed_stached(
        node, callback, processed_nodes, stashed_nodes, path_len, recursive, process=process, **kwargs, priority_map=priority_map
    )
    # callback( node, **kwargs)
    # MANAGE STASHED NODES
    prev_stashed_nodes = stashed_nodes.copy()
    loop_count = 0
    len_prev_processed_nodes = 0
    while len(stashed_nodes) > 0:
        loop_count = check_stashed_loop(
            stashed_nodes, prev_stashed_nodes, processed_nodes, len_prev_processed_nodes, loop_count
        )
        prev_stashed_nodes = stashed_nodes.copy()
        len_prev_processed_nodes = len(processed_nodes)
        if len(stashed_nodes) > 0:
            s_node = stashed_nodes.pop()
            # remove duplicates
            if s_node in stashed_nodes:
                stashed_nodes.remove(s_node)
            if kwargs.get("warn", False):
                logger.debug(
                    "{}:: {}: unstashed for processing ({})::{}".format(
                        callback.__name__, s_node.__class__, get_data_for_log(s_node), len(stashed_nodes)
                    )
                )
            warn = loop_count >= (9 * len(stashed_nodes) + 1)
            walktrhough_tricc_node_processed_stached(
                s_node,
                callback,
                processed_nodes,
                stashed_nodes,
                path_len,
                recursive,
                warn=warn,
                process=process,
                **kwargs,
                priority_map=priority_map
            )
            # if len(stashed_nodes) != len(prev_stashed_nodes):
            #     reorder_node_list(stashed_nodes, node.group, processed_nodes, priority_map)




# check if the all the prev nodes are processed
def is_ready_to_process(in_node, processed_nodes, strict=True, local=False, loop_count=0):
    if isinstance(in_node, TriccNodeSelectOption):
        node = in_node.select
    elif isinstance(in_node, (TriccNodeActivityStart, TriccNodeMainStart)):
        # check before
        return True
    else:
        node = in_node
    if hasattr(node, "prev_nodes"):
        # ensure the  previous node of the select are processed, not the option prev nodes
        for prev_node in node.prev_nodes:
            if is_prev_processed(prev_node, node, processed_nodes, local, loop_count) is False:
                return False
    return True


def is_prev_processed(prev_node, node, processed_nodes, local, loop_count=0 ):
    if hasattr(prev_node, "select"):
        if prev_node.select == node:
            return True
        else:
            return is_prev_processed(prev_node.select, node, processed_nodes, local, loop_count )

    if prev_node not in processed_nodes and (not local):
        # Only log detailed failures when we suspect dependency loops (loop_count > 5)
        if loop_count > 5:
            if isinstance(prev_node, TriccNodeExclusive):
                iterator = iter(prev_node.prev_nodes)
                p_n_node = next(iterator)
                logger.debug(
                    "is_ready_to_process:failed:via_excl: {} - {} > {} {}:{}".format(
                        get_data_for_log(p_n_node), prev_node.get_name(), node.__class__, node.get_name(), node.instance
                    )
                )

            else:
                logger.debug(
                    "is_ready_to_process:failed: {} -> {} {}:{}".format(
                        get_data_for_log(prev_node), node.__class__, node.get_name(), node.instance
                    )
                )

            logger.debug(
                "prev node node {}:{} for node {} not in processed".format(
                    prev_node.__class__, prev_node.get_name(), node.get_name()
                )
            )
        return False
    return True


def print_trace(node, prev_node, processed_nodes, stashed_nodes, history=[]):

    if node != prev_node:
        if node in processed_nodes:
            logger.warning(
                "print trace :: node {}  was the last not processed ({}):{}".format(
                    get_data_for_log(prev_node), node.id, ">".join(history)
                )
            )
            # processed_nodes.add(prev_node)
            return False
        elif node in history:
            logger.critical(
                "print trace :: CYCLE node {} found in history ({})".format(
                    get_data_for_log(prev_node), ">".join(history)
                )
            )
            exit(1)
        elif node in stashed_nodes:
            #            logger.debug("print trace :: node {}::{} in stashed".format(node.__class__,node.get_name()))
            return False
            # else:
        # logger.debug("print trace :: node {} not processed/stashed".format(node.get_name()))
    return True


def reverse_walkthrough(in_node, next_node, callback, processed_nodes, stashed_nodes, history=[]):
    # transform dead-end nodes
    if next_node == in_node and next_node not in stashed_nodes:
        # workaround fir loop
        return False

    if isinstance(in_node, TriccNodeSelectOption):
        node = in_node.select
    elif isinstance(in_node, TriccNodeActivityStart):
        node = in_node.activity
    else:
        node = in_node
    if callback(node, next_node, processed_nodes=processed_nodes, stashed_nodes=stashed_nodes):
        history.append(node)
        if isinstance(in_node, TriccNodeActivity):
            prev_nodes = set(in_node.get_end_nodes())
            for prev in prev_nodes:
                reverse_walkthrough(
                    prev,
                    next_node,
                    callback,
                    processed_nodes=processed_nodes,
                    stashed_nodes=stashed_nodes,
                    history=history,
                )
        if hasattr(node, "prev_nodes"):
            if node.prev_nodes:
                for prev in node.prev_nodes:
                    reverse_walkthrough(
                        prev,
                        node,
                        callback,
                        processed_nodes=processed_nodes,
                        stashed_nodes=stashed_nodes,
                        history=history,
                    )
            elif node in node.activity.calculates:
                reverse_walkthrough(
                    prev,
                    node.activity.root,
                    callback,
                    processed_nodes=processed_nodes,
                    stashed_nodes=stashed_nodes,
                    history=history,
                )

        if issubclass(node.__class__, TriccRhombusMixIn):
            if isinstance(node.reference, list):
                for ref in node.reference:
                    reverse_walkthrough(
                        ref,
                        node,
                        callback,
                        processed_nodes=processed_nodes,
                        stashed_nodes=stashed_nodes,
                        history=history,
                    )


def get_prev_node_by_name(processed_nodes, name, node):
    from tricc_oo.models.base import get_repeat

    node_repeat = get_repeat(node)
    # look for the node in the same activity
    last_calc = get_last_version(name, processed_nodes, repeat=node_repeat)
    if last_calc:
        return last_calc

    filtered = list(
        filter(
            lambda p_node: hasattr(p_node, "name")
            and p_node.name == name
            and get_repeat(p_node) == node_repeat
            and p_node.instance == node.instance
            and p_node.path_len <= node.path_len,
            processed_nodes,
        )
    )
    if len(filtered) == 0:
        filtered = list(
            filter(
                lambda p_node: hasattr(p_node, "name")
                and p_node.name == name
                and get_repeat(p_node) == node_repeat,
                processed_nodes,
            )
        )
    if len(filtered) > 0:
        return sorted(filtered, key=lambda x: x.path_len, reverse=False)[0]


MIN_LOOP_COUNT = 10


def iter_node_dependencies(node):
    """Yield (dependency, etype) for prev_nodes and expression/reference deps.

    etype is ``prev`` for graph predecessors and ``ref`` for expression/reference
    dependencies.  Collects from get_references() plus expression_reference /
    reference / relevance / trigger / applicability so empty ``reference=[]``
    does not hide expression_reference refs (same sources that block processing).
    """
    seen = set()

    def _dep_key(d):
        if isinstance(d, TriccReference):
            return ("ref", d.value)
        if d is None:
            return None
        return ("id", getattr(d, "id", None) or id(d))

    def _emit(d, etype):
        if d is None:
            return
        if isinstance(d, TriccNodeSelectOption):
            d = getattr(d, "select", d)
        key = (_dep_key(d), etype)
        if key in seen or key[0] is None:
            return
        seen.add(key)
        yield d, etype

    if hasattr(node, "prev_nodes") and node.prev_nodes:
        for p in node.prev_nodes:
            yield from _emit(p, "prev")

    # get_references() can return [] when reference is an empty list even if
    # expression_reference still holds TriccReference objects — also scan attrs.
    ref_sources = []
    if hasattr(node, "get_references"):
        try:
            ref_sources.append(node.get_references())
        except Exception:
            pass
    for attr in ("expression_reference", "reference", "relevance", "trigger", "applicability"):
        val = getattr(node, attr, None)
        if val is None:
            continue
        if hasattr(val, "get_references"):
            try:
                ref_sources.append(val.get_references())
            except Exception:
                pass
        elif isinstance(val, list):
            ref_sources.append(val)
        elif isinstance(val, TriccReference):
            ref_sources.append([val])

    for source in ref_sources:
        if not source:
            continue
        for r in source:
            if isinstance(r, TriccReference) or issubclass(r.__class__, TriccNodeBaseModel):
                yield from _emit(r, "ref")
            elif hasattr(r, "get_references"):
                try:
                    nested = r.get_references() or []
                except Exception:
                    nested = []
                for nr in nested:
                    yield from _emit(nr, "ref")


def generate_stashed_loop_mermaid(stashed_nodes, waited, looped, processed_nodes):
    """Generate Mermaid flowchart for stashed loop diagnostics.

    - Stashed nodes: orange
    - Processed dependants (part of processed graph): green
    - Unresolved TriccReference nodes: red
    - Other unresolved dependants (unprocessed): gray
    Includes stashed nodes and direct links (prev_nodes + expression references)
    between them and to processed / unprocessed / reference dependants.

    TriccReference dependencies are resolved by name to stashed, processed, or
    known activity nodes so edges are not incorrectly drawn as red stubs when the
    real target exists.
    """
    node_defs = {}  # nid -> label
    edge_set = set()  # (from_nid, to_nid, etype)
    class_map = {}  # nid -> 'stashed'|'processed'|'reference'|'other'

    # Build name -> nodes index from stashed/processed and their activities so
    # expression refs can resolve to unprocessed graph nodes (gray), not only
    # red TriccReference stubs.
    name_index = {}

    def _index_node(n):
        if n is None or isinstance(n, TriccReference):
            return
        name = getattr(n, "name", None)
        if name:
            name_index.setdefault(name, [])
            if n not in name_index[name]:
                name_index[name].append(n)
        activity = getattr(n, "activity", None)
        nodes_map = getattr(activity, "nodes", None) if activity is not None else None
        if nodes_map:
            for an in nodes_map.values():
                aname = getattr(an, "name", None)
                if aname:
                    name_index.setdefault(aname, [])
                    if an not in name_index[aname]:
                        name_index[aname].append(an)

    for n in list(stashed_nodes) + list(processed_nodes):
        _index_node(n)

    def get_node_id(n):
        if isinstance(n, TriccReference):
            base = f"ref_{n.value}"
        else:
            base = getattr(n, "id", None) or getattr(n, "name", None) or str(n)[:40]
        safe = re.sub(r"[^a-zA-Z0-9_]", "_", str(base))
        if not safe:
            safe = "node_unknown"
        if safe and safe[0].isdigit():
            safe = "n_" + safe
        return safe

    def get_label(n):
        if isinstance(n, TriccReference):
            return f"Reference<br/>{_safe_mermaid_text(n.value)}"
        try:
            nm = n.get_name()
        except Exception:
            nm = str(n)[:40]
        cls = n.__class__.__name__
        return f"{cls}<br/>{_safe_mermaid_text(nm)}"

    def _safe_mermaid_text(text, max_len=50):
        text = str(text).replace('"', "'").replace("\n", " ").replace("`", "'")
        if len(text) > max_len:
            text = text[: max_len - 3] + "..."
        return text

    def resolve_dep(d):
        """Map TriccReference / select-option wrappers to real graph nodes when known."""
        if d is None:
            return None
        if isinstance(d, TriccNodeSelectOption):
            d = getattr(d, "select", d)
        if isinstance(d, TriccReference):
            # Prefer clean name when option syntax name[label] is used
            ref_name = d.value
            if isinstance(ref_name, str) and ref_name.endswith("]") and "[" in ref_name:
                ref_name = ref_name.split("[", 1)[0]
            candidates = name_index.get(ref_name) or name_index.get(d.value) or []
            # Preference: stashed > processed > other (unprocessed)
            for pool in (stashed_nodes, processed_nodes):
                for n in candidates:
                    if n in pool:
                        return n
                for n in pool:
                    if getattr(n, "name", None) in (ref_name, d.value):
                        return n
            if candidates:
                return candidates[0]
            return d
        return d

    def classify(n):
        if isinstance(n, TriccReference):
            return "reference"
        if n in stashed_nodes:
            return "stashed"
        if n in processed_nodes:
            return "processed"
        return "other"

    def add_node(n, force_class=None):
        if n is None:
            return None
        n = resolve_dep(n)
        if n is None:
            return None
        nid = get_node_id(n)
        if nid not in node_defs:
            node_defs[nid] = get_label(n)
            _index_node(n)
        preferred = ("stashed", "processed")
        weaker = ("reference", "other")
        if force_class:
            existing = class_map.get(nid)
            if existing in preferred and force_class in weaker:
                pass
            else:
                class_map[nid] = force_class
        elif nid not in class_map:
            class_map[nid] = classify(n)
        return nid

    def add_edge(src, dst, etype=""):
        sid = add_node(src)
        did = add_node(dst)
        if sid and did and sid != did:
            key = (sid, did, etype)
            if key not in edge_set:
                edge_set.add(key)

    # Index parents by str(n) so waited/looped keys can be re-linked as edges
    str_to_node = {}
    for n in list(stashed_nodes) + list(processed_nodes):
        str_to_node[str(n)] = n

    # Collect direct dependencies for every stashed node
    for sn in list(stashed_nodes):
        add_node(sn, force_class="stashed")
        for dep, etype in iter_node_dependencies(sn):
            add_edge(sn, resolve_dep(dep), etype)

    # Waited/looped: always draw parent → dependency edges (not orphan nodes)
    for container, etype in ((looped, "loop"), (waited, "wait")):
        if not container:
            continue
        for parent_key, deplist in container.items():
            parent = str_to_node.get(parent_key)
            if parent is None:
                for sn in stashed_nodes:
                    if str(sn) == parent_key:
                        parent = sn
                        break
            for d in deplist or []:
                resolved = resolve_dep(d)
                edge_type = etype
                if isinstance(d, TriccReference) or isinstance(resolved, TriccReference):
                    edge_type = "ref"
                elif resolved in stashed_nodes:
                    edge_type = "loop" if etype == "loop" else "wait"
                if parent is not None:
                    add_edge(parent, resolved, edge_type)
                else:
                    # Still surface the dependency even if parent key is unknown
                    if isinstance(resolved, TriccReference):
                        add_node(resolved, force_class="reference")
                    elif resolved in stashed_nodes:
                        add_node(resolved, force_class="stashed")
                    elif resolved in processed_nodes:
                        add_node(resolved, force_class="processed")
                    else:
                        add_node(resolved)

    # Build mermaid source
    lines = ["flowchart TD"]
    for nid, label in node_defs.items():
        lines.append(f'    {nid}["{label}"]')

    for sid, did, etype in edge_set:
        if etype:
            lines.append(f"    {sid} -->|{etype}| {did}")
        else:
            lines.append(f"    {sid} --> {did}")

    # Class definitions
    lines.append("    classDef stashed fill:#ffa500,stroke:#333,color:#000")
    lines.append("    classDef processed fill:#90EE90,stroke:#333,color:#000")
    lines.append("    classDef reference fill:#ff6666,stroke:#333,color:#fff")
    lines.append("    classDef other fill:#cccccc,stroke:#333,color:#000")

    grouped = {"stashed": [], "processed": [], "reference": [], "other": []}
    for nid, cls in class_map.items():
        if cls in grouped:
            grouped[cls].append(nid)

    for cls_name, ids in grouped.items():
        if ids:
            lines.append(f"    class {','.join(ids)} {cls_name}")

    return "\n".join(lines)


def check_stashed_loop(stashed_nodes, prev_stashed_nodes, processed_nodes, len_prev_processed_nodes, loop_count):

    if (
        len(stashed_nodes) == len(prev_stashed_nodes)
        and set(stashed_nodes) == set(prev_stashed_nodes)
        and len(processed_nodes) == len_prev_processed_nodes
    ):
        loop_count += 1
        if loop_count > max(MIN_LOOP_COUNT, 11 * len(prev_stashed_nodes) + 1):
            logger.critical("Stashed node list was unchanged: loop likely or unresolved dependence")
            waited, looped = get_all_dependant(stashed_nodes, stashed_nodes, processed_nodes)
            logger.debug(f"{len(looped)} nodes waiting stashed nodes")
            logger.info("unresolved reference")
            for es_node in [n for n in stashed_nodes if isinstance(n, TriccReference)]:
                logger.info(
                    "Stashed node {}:{}|{} {}".format(
                        es_node.activity.get_name() if hasattr(es_node, "activity") else "",
                        es_node.activity.instance if hasattr(es_node, "activity") else "",
                        es_node.__class__,
                        es_node.get_name(),
                    )
                )
            for es_node in [
                node for node_list in looped.values() for node in node_list if isinstance(node, TriccReference)
            ]:
                logger.info(
                    "looped node {}:{}|{} {}".format(
                        es_node.activity.get_name() if hasattr(es_node, "activity") else "",
                        es_node.activity.instance if hasattr(es_node, "activity") else "",
                        es_node.__class__,
                        es_node.get_name(),
                    )
                )
            for es_node in [
                node for node_list in waited.values() for node in node_list if isinstance(node, TriccReference)
            ]:
                logger.info(
                    "waited node {}:{}|{} {}".format(
                        es_node.activity.get_name() if hasattr(es_node, "activity") else "",
                        es_node.activity.instance if hasattr(es_node, "activity") else "",
                        es_node.__class__,
                        es_node.get_name(),
                    )
                )
            logger.info("looped nodes")
            for dep_list in looped:
                for d in looped[dep_list]:
                    if str(d) in looped:
                        logger.critical("[{}] depends on [{}]".format(dep_list, str(d)))
                    else:
                        logger.error("[{}] depends on [{}]".format(dep_list, str(d)))
                if dep_list in waited:
                    for d in waited[dep_list]:
                        logger.warning("[{}] depends on [{}]".format(dep_list, str(d)))
            logger.info("waited nodes")
            for dep_list in waited:
                if dep_list not in looped:
                    for d in waited[dep_list]:
                        logger.warning("[{}] depends on [{}]".format(dep_list, d.get_name()))

            # Generate and log Mermaid diagram of the stashed situation
            try:
                mermaid_diagram = generate_stashed_loop_mermaid(stashed_nodes, waited, looped, processed_nodes)
                logger.info("=== STASHED LOOP MERMAID DIAGRAM (copy to https://mermaid.live) ===\n" + mermaid_diagram)
            except Exception as ex:
                logger.warning(f"Failed to generate stashed loop mermaid: {ex}")

            if len(stashed_nodes) == len(prev_stashed_nodes):
                exit(1)
    else:
        loop_count = 0
    return loop_count


def add_to_tree(tree, n, d):
    n_str = str(n)
    if n_str not in tree:
        tree[n_str] = []
    if d not in tree[n_str]:
        tree[n_str].append(d)
    return tree


def get_all_dependant(loop, stashed_nodes, processed_nodes, depth=0, waited=None, looped=None, path=None):
    if path is None:
        path = []
    if looped is None:
        looped = {}
    if waited is None:
        waited = {}
    all_dependant = OrderedSet()
    for n in loop:
        cur_path = path.copy()
        cur_path.append(n)
        dependant = OrderedSet()
        for d, _etype in iter_node_dependencies(n):
            dependant.add(d)
        for d in dependant:
            if d in path[:-1]:
                logger.warning(
                    f"loop {str(d)} already in path {'::'.join(map(str, path))}  "
                )
            if isinstance(d, TriccNodeSelectOption):
                d = d.select

            if isinstance(d, TriccReference):
                ref_name = d.value
                if isinstance(ref_name, str) and ref_name.endswith("]") and "[" in ref_name:
                    ref_name = ref_name.split("[", 1)[0]
                match_stashed = next(
                    (sn for sn in stashed_nodes if getattr(sn, "name", None) in (d.value, ref_name)),
                    None,
                )
                match_processed = next(
                    (pn for pn in processed_nodes if getattr(pn, "name", None) in (d.value, ref_name)),
                    None,
                )
                if match_processed is None:
                    if match_stashed is None:
                        waited = add_to_tree(waited, n, d)
                    else:
                        # Store the real stashed node so diagnostics (mermaid/logs) link correctly
                        looped = add_to_tree(looped, n, match_stashed)

            elif d not in processed_nodes:
                if d in stashed_nodes:
                    looped = add_to_tree(looped, n, d)
                else:
                    waited = add_to_tree(waited, n, d)
            all_dependant.add(d)
    if depth < MAX_DRILL:
        waited, looped = get_all_dependant(
            all_dependant, stashed_nodes, processed_nodes, depth + 1, waited, looped, path=cur_path
        )

    return waited, looped


MAX_DRILL = 3


def get_last_end_node(processed_nodes, process=None):
    end_name = "tricc_end_"
    if process:
        end_name += process
    return get_last_version(end_name, processed_nodes)


# Set the source next node to target and clean  next nodes of replace node


def set_prev_next_node(source_node, target_node, replaced_node=None, edge_only=False, activity=None):
    activity = activity or source_node.activity
    source_id, source_node = get_node_from_id(activity, source_node, edge_only)
    target_id, target_node = get_node_from_id(activity, target_node, edge_only)
    # if it is end node, attached it to the activity/page
    if not edge_only:
        set_prev_node(source_node, target_node, replaced_node, edge_only)
        set_next_node(source_node, target_node, replaced_node, edge_only)

    if activity and not any([(e.source == source_id) and (e.target == target_id) for e in activity.edges]):
        if issubclass(source_node.__class__, TriccNodeSelect):
            label = "continue"
        elif isinstance(source_node, TriccNodeRhombus):
            label = "yes"
        else:
            label = None
        activity.edges.append(TriccEdge(id=generate_id(), source=source_id, target=target_id, value=label))


def remove_prev_next(prev_node, next_node, activity=None):
    activity = activity or prev_node.activity
    if hasattr(prev_node, "next_nodes") and next_node in prev_node.next_nodes:
        prev_node.next_nodes.remove(next_node)
    if hasattr(next_node, "prev_nodes") and prev_node in next_node.prev_nodes:
        next_node.prev_nodes.remove(prev_node)

    for e in list(activity.edges):
        if e.target == getattr(next_node, "id", next_node) and e.source == getattr(prev_node, "id", prev_node):
            activity.edges.remove(e)


def set_next_node(source_node, target_node, replaced_node=None, edge_only=False, activity=None):
    activity = activity or source_node.activity
    replace_target = None
    if not edge_only:
        if replaced_node is not None and hasattr(source_node, "path") and replaced_node == source_node.path:
            source_node.path = target_node
        elif (
            replaced_node is not None and hasattr(source_node, "next_nodes") and replaced_node in source_node.next_nodes
        ):
            replace_target = True
            source_node.next_nodes.remove(replaced_node)
            if hasattr(replaced_node, "prev_nodes") and source_node in replaced_node.prev_nodes:
                replaced_node.prev_nodes.remove(source_node)
        # if replaced_node is not None and hasattr(target_node, 'next_nodes')
        #  and replaced_node in target_node.next_nodes:
        #    target_node.next_nodes.remove(replaced_node)
        if target_node not in source_node.next_nodes:
            source_node.next_nodes.add(target_node)
        # if rhombus in next_node of prev node and next node as ref
        if replaced_node is not None:
            rhombus_list = list(filter(lambda x: issubclass(x.__class__, TriccRhombusMixIn), source_node.next_nodes))
            for rhm in rhombus_list:
                if isinstance(rhm.reference, list):
                    if replaced_node in rhm.reference:
                        rhm.reference.remove(replaced_node)
                        rhm.reference.append(target_node)
    if target_node.id not in activity.nodes:
        activity.nodes[target_node.id] = target_node
    if replaced_node and replaced_node in replaced_node.activity.calculates:
        replaced_node.activity.calculates.remove(replaced_node)
    if replaced_node and replace_target:
        if replaced_node.id in replaced_node.activity.nodes:
            del replaced_node.activity.nodes[replaced_node.id]
        next_edges = set(
            [
                e for e in replaced_node.activity.edges
                if (e.target == replaced_node.id or e.target == replaced_node)
            ] + [
                e for e in activity.edges
                if (e.target == replaced_node.id or e.target == replaced_node)
            ]
        )
        if len(next_edges) == 0:
            for e in next_edges:
                e.target = target_node.id


# Set the target_node prev node to source and clean prev nodes of replace_node
def set_prev_node(source_node, target_node, replaced_node=None, edge_only=False, activity=None):
    activity = activity or source_node.activity
    replace_source = False
    # update the prev node of the target not if not an end node
    # update directly the prev node of the target
    if replaced_node is not None and hasattr(target_node, "path") and replaced_node == target_node.path:
        target_node.path = source_node
    if replaced_node is not None and hasattr(target_node, "prev_nodes") and replaced_node in target_node.prev_nodes:
        replace_source = True
        target_node.prev_nodes.remove(replaced_node)
        if hasattr(replaced_node, "next_nodes") and source_node in replaced_node.next_nodes:
            replaced_node.next_nodes.remove(source_node)
    # if replaced_node is not None and hasattr(source_node, 'prev_nodes') and replaced_node in source_node.prev_nodes:
    #    source_node.prev_nodes.remove(replaced_node)
    if source_node not in target_node.prev_nodes:
        target_node.prev_nodes.add(source_node)
    if source_node.id not in activity.nodes:
        activity.nodes[source_node.id] = source_node
    if replaced_node and replace_source:
        if replaced_node.id in replaced_node.activity.nodes:
            del replaced_node.activity.nodes[replaced_node.id]
        next_edges = set(
            [e for e in replaced_node.activity.edges if (e.source == replaced_node.id or e.source == replaced_node)]
            + [e for e in activity.edges if (e.source == replaced_node.id or e.source == replaced_node)]
        )
        if len(next_edges) == 0:
            for e in next_edges:
                e.target = target_node.id


def replace_node(old, new, page=None):
    if page is None:
        page = old.activity
    logger.debug("replacing node {} with node {} from page {}".format(old.get_name(), new.get_name(), page.get_name()))
    # list_node used to avoid updating a list in the loop
    list_nodes = []
    for prev_node in old.prev_nodes:
        list_nodes.append(prev_node)
    for prev_node in list_nodes:
        set_prev_next_node(prev_node, new, old)
    old.prev_nodes = set()
    list_nodes = []
    for next_node in old.next_nodes:
        list_nodes.append(next_node)
    for next_node in list_nodes:
        set_prev_next_node(new, next_node, old)
    old.next_nodes = set()
    if old in page.nodes:
        del page.nodes[old.id]
    page.nodes[new.id] = new

    for edge in page.edges:
        if edge.source == old.id:
            edge.source = new.id
        if edge.target == old.id:
            edge.target = new.id


def _swap_node_references(old_node, new_node):
    """Rewrite prev/next object references from old_node to new_node (same id safe)."""
    for nxt in list(getattr(old_node, "next_nodes", None) or []):
        if hasattr(nxt, "prev_nodes") and old_node in nxt.prev_nodes:
            nxt.prev_nodes.remove(old_node)
            nxt.prev_nodes.add(new_node)
        if hasattr(nxt, "path") and getattr(nxt, "path", None) is old_node:
            nxt.path = new_node
    for prev in list(getattr(old_node, "prev_nodes", None) or []):
        if hasattr(prev, "next_nodes") and old_node in prev.next_nodes:
            prev.next_nodes.remove(old_node)
            prev.next_nodes.add(new_node)
        if hasattr(prev, "path") and getattr(prev, "path", None) is old_node:
            prev.path = new_node
    new_node.prev_nodes = set(getattr(old_node, "prev_nodes", None) or set())
    new_node.next_nodes = set(getattr(old_node, "next_nodes", None) or set())
    old_node.prev_nodes = set()
    old_node.next_nodes = set()


def convert_structural_node_to_bridge(node, activity, label_prefix="snippet"):
    """
    Replace an activity start/end (or other structural node) with a TriccNodeBridge.

    Keeps the same id so existing edges remain valid.
    """
    if isinstance(node, TriccNodeBridge):
        return node

    bridge = TriccNodeBridge(
        id=node.id,
        group=getattr(node, "group", activity),
        activity=activity,
        label=f"{label_prefix}: {node.get_name()}",
        name=getattr(node, "name", None) or f"path_{node.id}",
        path_len=getattr(node, "path_len", 0) or 0,
        instance=getattr(node, "instance", 0) or 0,
        base_instance=getattr(node, "base_instance", None),
    )
    priority = getattr(node, "priority", None)
    if priority is not None:
        bridge.priority = priority

    _swap_node_references(node, bridge)

    if node.id in activity.nodes:
        del activity.nodes[node.id]
    activity.nodes[bridge.id] = bridge

    if getattr(activity, "root", None) is node or getattr(activity, "root", None) and activity.root.id == node.id:
        activity.root = bridge

    if node in getattr(activity, "calculates", []):
        activity.calculates.remove(node)

    return bridge


def _snippet_end_nodes(activity):
    """
    All terminal nodes of a cloned module that must not land on the parent activity.

    Union of get_end_nodes() and every end/activity_end in activity.nodes (get_end_nodes
    alone can miss TriccNodeEnd when root is activity_start).
    """
    ends = list(activity.get_end_nodes())
    seen = {e.id for e in ends}
    for n in activity.nodes.values():
        if isinstance(n, (TriccNodeEnd, TriccNodeActivityEnd)) and n.id not in seen:
            ends.append(n)
            seen.add(n.id)
    return ends


def _resolve_activity_node(activity, node_or_id):
    """Resolve a node object or id to a node living in activity.nodes."""
    if node_or_id is None:
        return None
    if issubclass(getattr(node_or_id, "__class__", object), TriccBaseModel) and getattr(node_or_id, "id", None) in activity.nodes:
        # Prefer the object stored on the activity (same id, current instance graph)
        return activity.nodes.get(node_or_id.id, node_or_id)
    nid = getattr(node_or_id, "id", node_or_id)
    return activity.nodes.get(nid)


def sync_prev_next_from_edges(activity, node_ids=None):
    """
    Rebuild prev_nodes/next_nodes from activity.edges.

    After snippet inject, edges are the source of truth; object-level prev/next can be
    stale (especially when the parent page is itself an activity instance).
    If node_ids is set, only those nodes and their edge-neighbors are rebuilt.
    """
    if node_ids is not None:
        node_ids = set(node_ids)
        affected_ids = set(node_ids)
        for edge in activity.edges:
            sid = getattr(edge.source, "id", edge.source)
            tid = getattr(edge.target, "id", edge.target)
            if sid in node_ids or tid in node_ids:
                affected_ids.add(sid)
                affected_ids.add(tid)
    else:
        affected_ids = set(activity.nodes.keys())

    for nid in affected_ids:
        n = activity.nodes.get(nid)
        if n is None:
            continue
        if hasattr(n, "prev_nodes"):
            n.prev_nodes = OrderedSet()
        if hasattr(n, "next_nodes"):
            n.next_nodes = OrderedSet()

    for edge in activity.edges:
        sid = getattr(edge.source, "id", edge.source)
        tid = getattr(edge.target, "id", edge.target)
        if sid not in affected_ids and tid not in affected_ids:
            continue
        src = activity.nodes.get(sid)
        tgt = activity.nodes.get(tid)
        if src is None or tgt is None:
            continue
        if hasattr(src, "next_nodes") and tgt not in src.next_nodes:
            src.next_nodes.add(tgt)
        if hasattr(tgt, "prev_nodes") and src not in tgt.prev_nodes:
            tgt.prev_nodes.add(src)


def replace_snippet_ends_with_bridge(activity):
    """
    Replace all end / activity_end nodes of a snippet clone with one exit bridge.

    The bridge takes over every end's prev_nodes (and incoming edges). All end nodes
    are removed so they cannot mark the parent activity as "processed" later
    (see walktrhough_tricc_node_processed_stached end-node handling).

    Returns the exit TriccNodeBridge, or None if the activity has no ends.
    """
    ends = _snippet_end_nodes(activity)
    if not ends:
        logger.warning(f"Snippet activity {activity.get_name()} has no end nodes")
        return None

    end_ids = {e.id for e in ends}
    # Union of predecessors that feed any end
    prev_nodes = set()
    for end in ends:
        for prev in list(getattr(end, "prev_nodes", None) or set()):
            prev_nodes.add(prev)
        # Also collect from edges (prev_nodes may be incomplete at clone time)
        for edge in activity.edges:
            if edge.target == end.id or edge.target == end:
                src_id = getattr(edge.source, "id", edge.source)
                src = activity.nodes.get(src_id)
                if src is not None and not isinstance(src, (TriccNodeEnd, TriccNodeActivityEnd)):
                    prev_nodes.add(src)

    # Include activity.instance so two injects of the same module never share an exit id
    # (processed_nodes is id-equality based across the whole form).
    bridge_id = generate_id(
        f"snippet_exit{activity.id}{getattr(activity, 'instance', 0)}{''.join(sorted(end_ids))}"
    )
    exit_bridge = TriccNodeBridge(
        id=bridge_id,
        group=getattr(activity, "group", activity) or activity,
        activity=activity,
        label=f"snippet_exit: {activity.get_name()}",
        name=f"path_{bridge_id}",
        path_len=max((getattr(e, "path_len", 0) or 0) for e in ends) if ends else 0,
        instance=getattr(activity, "instance", 0) or 0,
    )
    exit_bridge.prev_nodes = set()
    exit_bridge.next_nodes = set()
    activity.nodes[exit_bridge.id] = exit_bridge

    # Rewire predecessors → exit bridge; drop edges that touched ends
    new_edges = []
    seen_prev_edge = set()
    for edge in list(activity.edges):
        src_id = getattr(edge.source, "id", edge.source)
        tgt_id = getattr(edge.target, "id", edge.target)
        if tgt_id in end_ids:
            # Incoming to an end → point at the exit bridge (dedupe)
            key = (src_id, exit_bridge.id)
            if key not in seen_prev_edge:
                edge.target = exit_bridge.id
                new_edges.append(edge)
                seen_prev_edge.add(key)
            continue
        if src_id in end_ids:
            # Outgoing from an end (unusual) → re-source from exit bridge
            edge.source = exit_bridge.id
            new_edges.append(edge)
            continue
        new_edges.append(edge)
    activity.edges = new_edges

    # Object-level prev/next: detach ends, attach bridge
    for prev in prev_nodes:
        if hasattr(prev, "next_nodes"):
            for end in ends:
                if end in prev.next_nodes:
                    prev.next_nodes.remove(end)
            prev.next_nodes.add(exit_bridge)
        if hasattr(prev, "path"):
            for end in ends:
                if getattr(prev, "path", None) is end:
                    prev.path = exit_bridge
        exit_bridge.prev_nodes.add(prev)

    for end in ends:
        for nxt in list(getattr(end, "next_nodes", None) or set()):
            if hasattr(nxt, "prev_nodes") and end in nxt.prev_nodes:
                nxt.prev_nodes.remove(end)
                nxt.prev_nodes.add(exit_bridge)
            exit_bridge.next_nodes.add(nxt)
        end.prev_nodes = set()
        end.next_nodes = set()
        if end.id in activity.nodes:
            del activity.nodes[end.id]
        if end in getattr(activity, "calculates", []):
            activity.calculates.remove(end)

    return exit_bridge


def _unregister_activity_instance(base_activity, clone):
    """Avoid polluting the shared instances map used by positive instance gotos."""
    base = base_activity.base_instance or base_activity
    if hasattr(base, "instances") and clone.instance in base.instances:
        if base.instances[clone.instance] is clone:
            del base.instances[clone.instance]


def _reparent_snippet_node(node, parent_activity, clone_activity):
    node.activity = parent_activity
    group = getattr(node, "group", None)
    if group is None or group is clone_activity or getattr(group, "id", None) == clone_activity.id:
        node.group = parent_activity
    elif hasattr(group, "activity"):
        group.activity = parent_activity


def import_activity_nodes_into_parent(clone, parent):
    """Move cloned activity nodes/edges/calculates/groups into the parent activity.

    Returns the set of imported node ids (for prev/next rebuild).
    """
    imported_ids = set()
    for node in list(clone.nodes.values()):
        # Never lift terminal ends into the parent (breaks activity-processed detection)
        if isinstance(node, (TriccNodeEnd, TriccNodeActivityEnd)):
            logger.warning(
                f"Skipping residual end {node.get_name()} during snippet import into {parent.get_name()}"
            )
            continue
        _reparent_snippet_node(node, parent, clone)
        # options / nested select options
        if isinstance(node, TriccNodeSelect) and getattr(node, "options", None):
            for opt in node.options.values():
                _reparent_snippet_node(opt, parent, clone)
                parent.nodes[opt.id] = opt
                imported_ids.add(opt.id)
        parent.nodes[node.id] = node
        imported_ids.add(node.id)

    for edge in list(clone.edges):
        parent.edges.append(edge)

    for calc in list(clone.calculates):
        if isinstance(calc, (TriccNodeEnd, TriccNodeActivityEnd)):
            continue
        _reparent_snippet_node(calc, parent, clone)
        if calc.id not in parent.nodes:
            parent.nodes[calc.id] = calc
            imported_ids.add(calc.id)
        if calc not in parent.calculates:
            parent.calculates.append(calc)

    for group in list(clone.groups.values()):
        if hasattr(group, "activity"):
            group.activity = parent
        if getattr(group, "group", None) is clone or getattr(group, "group", None) is None:
            group.group = parent
        parent.groups[group.id] = group

    return imported_ids


# Monotonic counter so every snippet inject gets distinct make_instance IDs even when
# several gotos share the same caller.instance and the same module template.
_snippet_inject_seq = 0


def clone_activity_for_snippet(goto, target_activity):
    """
    Clone a target activity for snippet injection (unique IDs, not registered for reuse).

    Caller should run linking_nodes on the clone before inject_activity_as_snippet,
    because make_instance resets prev_nodes/next_nodes.

    Instance numbers must be unique per inject. Node ids are generate_id(base_id + instance);
    if two injects reuse the same number, processed_nodes (keyed by id equality) treats the
    second exit bridge as already processed and never stashes that activity's end — the
    outer wait on the caller activity then hangs forever.
    """
    global _snippet_inject_seq
    from tricc_oo.converters.xml_to_tricc import apply_goto_repeat_to_activity

    if not isinstance(target_activity, TriccNodeActivity):
        logger.critical(
            f"goto snippet {goto.get_name()} link is not an activity: {goto.link}"
        )
        exit(1)

    # Resolve the template page (not a prior instance of the module)
    template = target_activity.base_instance or target_activity
    _snippet_inject_seq += 1
    caller_inst = getattr(getattr(goto, "activity", None), "instance", 0) or 0
    # High band + caller instance + goto id entropy + monotonic seq → unique node ids
    goto_key = abs(hash(str(getattr(goto, "id", "")) + str(getattr(goto, "name", "")))) % 10000
    snippet_nb = 900000 + (int(caller_inst) * 100000) + (goto_key * 10) + (_snippet_inject_seq % 10)
    # Ensure not colliding with any live or previously used instance slot
    used = set(getattr(template, "instances", {}) or {})
    # Also reserve numbers that may still be referenced after unregister
    while snippet_nb in used:
        snippet_nb += 1
        used.add(snippet_nb)

    clone = template.make_instance(snippet_nb)
    _unregister_activity_instance(template, clone)
    apply_goto_repeat_to_activity(goto, clone)
    return clone


def sync_slot_versions_on_activity(activity, focus_names=None):
    """Renumber ``version`` / ``last`` for each export-name bucket on an activity.

    Used after snippet inject so cloned same-name nodes (and any pre-existing peers
    already on the parent) get unique export versions immediately, not only later
    when ``load_calculate`` walks the graph.

    Buckets follow export base rules: ``repeat > 1`` is isolated by repeat;
    ``repeat <= 1`` (incl. ``-1``) share one version space per name.
    """
    buckets = defaultdict(list)
    pool = list(getattr(activity, "nodes", {}).values())
    pool.extend(getattr(activity, "calculates", []) or [])
    for n in pool:
        if isinstance(n, (TriccNodeSelectOption, TriccNodeEnd, TriccNodeActivityEnd)):
            continue
        name = getattr(n, "name", None)
        if not name:
            continue
        if focus_names is not None and name not in focus_names:
            continue
        buckets[_export_version_bucket_key(name, get_repeat(n))].append(n)

    for _key, peers in buckets.items():
        if len(peers) < 2:
            continue
        ordered = sorted(
            peers,
            key=lambda n: (
                getattr(n, "path_len", 0) or 0,
                getattr(n, "instance", 0) or 0,
                str(getattr(n, "id", "")),
            ),
        )
        for i, peer in enumerate(ordered, start=1):
            peer.version = i
            peer.last = i == len(ordered)
            if hasattr(peer, "export_name"):
                peer.export_name = None


def inject_activity_as_snippet(goto, parent_page, clone):
    """
    Inline an already-cloned (and preferably already-linked) activity into parent_page
    in place of a goto (instance == -1).

    Returns the entry TriccNodeBridge that should replace the goto as the link target.
    """
    if not isinstance(clone, TriccNodeActivity):
        logger.critical(
            f"goto snippet {goto.get_name()}: expected cloned activity, got {type(clone)}"
        )
        exit(1)

    if not isinstance(clone.root, (TriccNodeActivityStart, TriccNodeBridge, TriccNodeMainStart)):
        logger.warning(
            f"Snippet clone {clone.get_name()} root type is {type(clone.root)}; "
            "expected activity_start"
        )

    # Ends first (while root is still activity_start so end detection stays reliable),
    # then convert start → entry bridge.
    exit_bridge = replace_snippet_ends_with_bridge(clone)
    entry = convert_structural_node_to_bridge(clone.root, clone, label_prefix="snippet_entry")
    if exit_bridge is None:
        # No ends: still import content; exit wiring only if goto has successors
        exit_bridge = entry

    # Safety: never import residual end/activity_end nodes into the parent
    for nid, n in list(clone.nodes.items()):
        if isinstance(n, (TriccNodeEnd, TriccNodeActivityEnd)):
            logger.warning(
                f"Removing residual end node {n.get_name()} from snippet before import into {parent_page.get_name()}"
            )
            del clone.nodes[nid]
    clone.calculates = [
        c for c in getattr(clone, "calculates", []) or []
        if not isinstance(c, (TriccNodeEnd, TriccNodeActivityEnd))
    ]

    imported_ids = import_activity_nodes_into_parent(clone, parent_page)
    imported_ids.add(entry.id)
    imported_ids.add(exit_bridge.id)

    # Capture boundary neighbors BEFORE mutating goto / edges.
    # Walkthrough only follows next_nodes (not edges); exit→successors must be set
    # or activity_end never reaches stashed_nodes and waits on the caller activity stall.
    goto_id = goto.id
    predecessors = []
    successors = []
    seen_prev = set()
    seen_next = set()

    for edge in list(parent_page.edges):
        src_id = getattr(edge.source, "id", edge.source)
        tgt_id = getattr(edge.target, "id", edge.target)
        if tgt_id == goto_id or edge.target == goto:
            prev = _resolve_activity_node(parent_page, edge.source)
            if prev is not None and prev.id not in seen_prev:
                predecessors.append(prev)
                seen_prev.add(prev.id)
        if src_id == goto_id or edge.source == goto:
            nxt = _resolve_activity_node(parent_page, edge.target)
            if nxt is not None and nxt.id not in seen_next:
                successors.append(nxt)
                seen_next.add(nxt.id)

    for prev in list(getattr(goto, "prev_nodes", None) or set()):
        prev = _resolve_activity_node(parent_page, prev) or prev
        pid = getattr(prev, "id", None)
        if pid and pid not in seen_prev:
            predecessors.append(prev)
            seen_prev.add(pid)

    for nxt in list(getattr(goto, "next_nodes", None) or set()):
        nxt = _resolve_activity_node(parent_page, nxt) or nxt
        nid = getattr(nxt, "id", None)
        if nid and nid not in seen_next:
            successors.append(nxt)
            seen_next.add(nid)

    # Also catch nodes that still list the goto in prev_nodes (edge may already be gone)
    for n in list(parent_page.nodes.values()):
        if n is goto:
            continue
        if hasattr(n, "prev_nodes") and goto in n.prev_nodes:
            if n.id not in seen_next:
                successors.append(n)
                seen_next.add(n.id)
        if hasattr(n, "next_nodes") and goto in n.next_nodes:
            if n.id not in seen_prev:
                predecessors.append(n)
                seen_prev.add(n.id)

    # Rewire parent edges that touched the goto
    for edge in list(parent_page.edges):
        if edge.target == goto_id or edge.target == goto:
            edge.target = entry.id
        if edge.source == goto_id or edge.source == goto:
            edge.source = exit_bridge.id

    # Ensure an edge exists for every boundary link (set_prev_next_node is edge-aware)
    for prev in predecessors:
        set_prev_next_node(prev, entry, replaced_node=goto, activity=parent_page)
    for nxt in successors:
        set_prev_next_node(exit_bridge, nxt, replaced_node=goto, activity=parent_page)

    if not successors:
        logger.warning(
            "snippet inject for {} into {}: exit bridge has no successors "
            "(activity_end / post-goto nodes may never enter stashed_nodes)".format(
                goto.get_name(), parent_page.get_name()
            )
        )

    goto.prev_nodes = OrderedSet()
    goto.next_nodes = OrderedSet()

    if goto_id in parent_page.nodes:
        del parent_page.nodes[goto_id]
    elif goto in parent_page.nodes.values():
        for k, v in list(parent_page.nodes.items()):
            if v is goto:
                del parent_page.nodes[k]
                break

    if goto in getattr(parent_page, "calculates", []):
        parent_page.calculates.remove(goto)

    # Rebuild imported subgraph from edges, then force exit→successor / prev→entry
    # (sync can miss links that only lived on prev/next without an edge).
    sync_prev_next_from_edges(parent_page, imported_ids)
    for prev in predecessors:
        prev = _resolve_activity_node(parent_page, prev) or prev
        set_prev_next_node(prev, entry, activity=parent_page)
    for nxt in successors:
        nxt = _resolve_activity_node(parent_page, nxt) or nxt
        set_prev_next_node(exit_bridge, nxt, activity=parent_page)

    if not exit_bridge.next_nodes and successors:
        # Last resort: object-level only (should not happen if set_prev_next_node worked)
        for nxt in successors:
            nxt = _resolve_activity_node(parent_page, nxt) or nxt
            if hasattr(exit_bridge, "next_nodes"):
                exit_bridge.next_nodes.add(nxt)
            if hasattr(nxt, "prev_nodes"):
                nxt.prev_nodes.add(exit_bridge)

    # After inlining, same concept names may already exist on the parent (from the
    # caller graph or a previous inject). Renumber versions for those slots so
    # export names stay unique even before load_calculate.
    imported_names = set()
    for nid in imported_ids:
        n = parent_page.nodes.get(nid)
        if n is not None and getattr(n, "name", None):
            imported_names.add(n.name)
    for calc in getattr(parent_page, "calculates", []) or []:
        if getattr(calc, "name", None) and calc.id in imported_ids:
            imported_names.add(calc.name)
    if imported_names:
        sync_slot_versions_on_activity(parent_page, imported_names)

    logger.debug(
        "injected activity {} as snippet into {} (entry={}, exit={}, successors={})".format(
            clone.get_name(),
            parent_page.get_name(),
            entry.get_name(),
            exit_bridge.get_name(),
            len(successors),
        )
    )
    return entry


def replace_prev_next_node(prev_node, next_node, old_node, force=False):
    replace_prev_node(prev_node, next_node, old_node)
    replace_next_node(prev_node, next_node, old_node)


def replace_prev_node(prev_node, next_node, old_node, force=False):
    # create a copy pf the list
    list_nodes = list(next_node.prev_nodes)
    # replace in case old node is found
    for p_n_node in list_nodes:
        if p_n_node == old_node or force:
            set_prev_next_node(prev_node, next_node, old_node)


def replace_next_node(prev_node, next_node, old_node):
    list_nodes = list(prev_node.next_nodes)
    for n_p_node in list_nodes:
        if n_p_node == old_node:
            set_prev_next_node(prev_node, next_node, old_node)


# Priority constants
POPULATE_PRIORITY = 1000
SAME_GROUP_PRIORITY = 70
PARENT_GROUP_PRIORITY = 60
ACTIVE_ACTIVITY_PRIORITY = 50
NON_START_ACTIVITY_PRIORITY = 40
ACTIVE_ACTIVITY_LOWER_PRIORITY = 30
FOLLOW_NODE = 4
FLOW_CALCULATE_NODE_PRIORITY_TOP_UP = 3
RHOMBUS_PRIORITY_TO_UP = 3
MAX_AUTO_PRIORITY = 76
   
def reorder_node_list(node_list, group, processed_nodes, priority_map = None):
    # Cache active activities for O(1) lookup
    if priority_map is None:
        priority_map = {}
    active_activities = {n.activity for n in processed_nodes}
    if not group.id in priority_map:
        priority_map[group.id] = {}
    def get_priority(node):
        if isinstance(node, TriccNodePopulate):
            return POPULATE_PRIORITY
        if (getattr(node, "repeat", None) or 1) < 1:
            return POPULATE_PRIORITY
        explicit_priority = getattr(node, "priority", None) or 0
        if node.id in priority_map[group.id]:
            return priority_map[group.id][node.id]
        if (
            (not explicit_priority and  
            issubclass(node.__class__, TriccNodeDisplayCalculateBase) 
            and not node.prev_nodes) or
            isinstance(node, (TriccNodeMainStart, TriccNodeActivityStart))
        ):    
            return get_priority(node.activity)           
        if isinstance(node, (TriccNodeSelectOption)):
            return get_priority(node.select)

        # Cache attributes to avoid repeated getattr calls
        
        priority = int(explicit_priority or 0)
        node_group = getattr(node, "group", None)
        activity = getattr(node, "activity", None)

        # Check for same group
        if group is not None and node_group and node_group.id == group.id:
            priority += SAME_GROUP_PRIORITY 
        # Check for parent group
        elif hasattr(group, "group") and group.group and node_group and node_group.id == group.group.id:
            priority += PARENT_GROUP_PRIORITY
        # Check for active activities (not main)
        elif activity and isinstance(activity.root, TriccNodeActivityStart) and activity in active_activities:
            priority += ACTIVE_ACTIVITY_PRIORITY
        # Check for non main activities
        elif activity and isinstance(activity.root, TriccNodeActivityStart):
            priority += NON_START_ACTIVITY_PRIORITY
        # Check for active activities (lower priority)
        elif activity and activity in active_activities:
            priority += ACTIVE_ACTIVITY_LOWER_PRIORITY
        # Check for rhombus nodes
        

        if (
            issubclass(node.__class__, TriccNodeDisplayCalculateBase) or
            isinstance(node, TriccNodeEnd)
        ) and not isinstance(node, TriccNodeActivityEnd) and hasattr(node, 'prev_nodes') and len(node.prev_nodes) > 0:
            priority += FLOW_CALCULATE_NODE_PRIORITY_TOP_UP
        elif issubclass(node.__class__, TriccRhombusMixIn):
            priority += RHOMBUS_PRIORITY_TO_UP
        if node.prev_nodes and not explicit_priority and not isinstance(node, TriccNodeMainStart):
            prev_priority = max(get_priority(p) for p in node.prev_nodes)
            if prev_priority >  MAX_AUTO_PRIORITY:
                priority = max(priority, prev_priority)
        if isinstance(node, TriccNodeSelectNotAvailable):
            priority += FOLLOW_NODE
        priority_map[group.id][node.id] = priority
        
        return priority

    # Sort in place, highest priority first
    # logger.debug(f"Reordering node_list for group {group.id if group else 'None'}: pre {[n.get_name() for n in node_list]}")
    node_list.sort(key=get_priority, reverse=True)
    # logger.debug(f"Post reorder: {[n.get_name() for n in node_list]}")
    #print(dict(zip([n.get_name() for n in node_list], list(map(get_priority, node_list)))))


def loop_info(loop, **kwargs):
    logger.critical("dependency details")
    for n in loop:
        i = 0
        logger.critical(f"{i}: {n.__class__}::{n.get_name()}")
        i += 1


def has_loop(
    node, processed_nodes, stashed_nodes, warn, node_path=[], action_on_loop=loop_info, action_on_other=None, **kwargs
):
    next_nodes = get_extended_next_nodes(node)
    for next_node in next_nodes:
        if next_node in node_path:
            loop_start_key = node_path.index(next_node)
            loop = node_path[loop_start_key:]
            loop.append(node)
            loop.append(next_node)
            action_on_loop(loop, **kwargs)
            return False
    if callable(action_on_other):
        action_on_other(next_node, **kwargs)
    return True


def get_extended_next_nodes(node):

    nodes = node.next_nodes if hasattr(node, "next_nodes") else set()
    if issubclass(node.__class__, TriccNodeSelect):
        for o in node.options.values():
            nodes = nodes | o.next_nodes
    if isinstance(node, (TriccNodeActivity)):
        nodes = nodes | node.root.next_nodes
    return nodes


# calculate or retrieve a node expression
def get_node_expression(in_node, processed_nodes, get_overall_exp=False, is_prev=False, negate=False, process=None):
    # in case of calculate we only use the select multiple if none is not selected
    expression = None
    negate_expression = None
    node = in_node
    if isinstance(node, (TriccNodeActivityStart, TriccNodeMainStart)):
        if is_prev and get_overall_exp:
            expression = get_node_expression(
                node.activity,
                processed_nodes=processed_nodes,
                get_overall_exp=True,
                is_prev=is_prev,
                negate=negate,
                process=process,
            )
            if isinstance(node, TriccNodeMainStart):
                expression = get_applicability_expression(node.activity, processed_nodes, process, expression)
        elif isinstance(node, (TriccNodeActivityStart)):
            return TriccStatic(True)

    elif isinstance(node, TriccNodeWait):
        if is_prev:
            # the wait don't do any calculation with the reference it is only use to wait until the reference are valid
            return get_node_expression(
                node.path,
                processed_nodes=processed_nodes,
                get_overall_exp=get_overall_exp,
                is_prev=True,
                process=process,
            )
        else:
            # it is a empty calculate
            return None
    elif isinstance(node, TriccNodeRhombus):
        expression = get_rhombus_terms(node, processed_nodes, process=process)
        negate_expression = not_clean(expression)
        if node.path is None:
            if len(node.prev_nodes) == 1:
                node.path = list(node.prev_nodes)[0]
            elif len(node.prev_nodes) > 1:
                logger.critical(f"missing path for Rhombus {node.get_name()}")
                exit(1)
        prev_exp = get_node_expression(
            node.path, processed_nodes=processed_nodes, get_overall_exp=get_overall_exp, is_prev=True, process=process
        )
        if prev_exp:
            prev_exp = prev_exp.copy(keep_node=True)
        if prev_exp and expression:
            expression = and_join([prev_exp, expression])
            negate_expression = and_join([prev_exp, negate_expression])

        elif prev_exp:

            logger.error(f"useless rhombus {node.get_name()}")
            expression = prev_exp
            negate_expression = prev_exp
            logger.critical(f"Rhombus without expression {node.get_name()}")
    elif is_prev and issubclass(node.__class__, TriccNodeDisplayCalculateBase):
        expression = TriccOperation(TriccOperator.ISTRUE, [node])
        prev_exp_overall = get_node_expression(
            node,
            processed_nodes=processed_nodes,
            get_overall_exp=False,
            is_prev=False,
            process=process,
            negate=negate
        )
        if prev_exp_overall in [TriccStatic(True), TriccStatic(False)]:
            expression = prev_exp_overall
    elif hasattr(node, "expression_reference") and isinstance(node.expression_reference, TriccOperation):
        # if issubclass(node.__class__, TriccNodeDisplayCalculateBase):
        #     expression = TriccOperation(
        #         TriccOperator.CAST_NUMBER,
        #         [node.expression_reference])
        # else:
        expression = node.expression_reference
    elif is_prev and isinstance(node, TriccNodeSelectOption):
        if negate:
            negate_expression = get_selected_option_expression(node, negate)
        else:
            expression = get_selected_option_expression(node, negate)
        # TODO remove that and manage it on the "Save" part
    elif is_prev and isinstance(node, TriccNodeSelectNotAvailable):
        expression = TriccOperation(TriccOperator.SELECTED, [node, TriccStatic(1)])
    elif issubclass(node.__class__, TriccNodeCalculateBase):
        if negate:
            negate_expression = get_calculation_terms(
                node, processed_nodes=processed_nodes, get_overall_exp=get_overall_exp, negate=True, process=process
            )
        else:
            expression = get_calculation_terms(
                node, processed_nodes=processed_nodes, get_overall_exp=get_overall_exp, process=process
            )

    elif (
        (not is_prev or not ONE_QUESTION_AT_A_TIME)
        and hasattr(node, "relevance")
        and isinstance(node.relevance, (TriccOperation, TriccStatic))
        and getattr(node, 'is_sequence_defined', False)
        and not get_overall_exp
    ):
        expression = node.relevance
    elif (
        ONE_QUESTION_AT_A_TIME
        and is_prev and not get_overall_exp 
        and hasattr(node, "required") 
        and node.required
        and getattr(node, 'is_sequence_defined', False)
    ):
        expression = get_required_node_expression(node)
    if expression is None:
        expression = get_prev_node_expression(
            node,
            activity=node.activity,
            processed_nodes=processed_nodes,
            get_overall_exp=get_overall_exp,
            process=process
        )
        # in_node not in processed_nodes is need for calculates that can but run after the end of the activity
    # if isinstance(node, TriccNodeActivitiy) and not prev:
    # expression = get_applicability_expression(node, processed_nodes, process, expression)
    # expression = get_prev_instance_skip_expression(node, processed_nodes, process, expression)
    # expression = get_process_skip_expression(node, processed_nodes, process, expression)
    if negate:
        if negate_expression is not None:
            return negate_expression
        elif expression is not None:
            return negate_term(expression)
        else:
            logger.critical("exclusive can not negate None from {}".format(node.get_name()))
            # exit(1)
    else:
        return expression


def get_applicability_expression(node, processed_nodes, process, expression=None):
    if isinstance(node.applicability, (TriccStatic, TriccOperation, TriccReference)):
        if expression:
            expression = and_join([node.applicability, expression])
        else:
            expression = node.applicability

    return expression


def get_prev_instance_skip_expression(node, processed_nodes, process, expression=None):
    if node.base_instance is not None:
        expression_inputs = []
        node_repeat = get_repeat(node)
        past_instances = [n for n in processed_nodes if getattr(n.base_instance, "id", None) == node.base_instance.id and node != n]
        for past_instance in [n for n in past_instances if get_repeat(n) == node_repeat]:
            add_sub_expression(
                expression_inputs,
                get_node_expression(
                    past_instance, processed_nodes=processed_nodes, get_overall_exp=True, is_prev=True, process=process
                ),
            )
        if expression and expression_inputs:
            expression = nand_join(expression, or_join(expression_inputs))
        elif expression_inputs:
            expression = negate_term(or_join(expression_inputs))
    return expression


# end def
def get_process_skip_expression(node, processed_nodes, process, expression=None):
    list_ends = [x for x in processed_nodes if isinstance(x, TriccNodeEnd)]
    if list_ends:
        end_expressions = []
        f_end_expression = get_end_expression(list_ends)
        if f_end_expression:
            end_expressions.append(f_end_expression)
        b_end_expression = get_end_expression(list_ends, "pause")
        if b_end_expression:
            end_expressions.append(b_end_expression)
        process_index = None
        if process and process[0] in PROCESSES:
            process_index = PROCESSES.index(process[0])
        if process_index is not None:
            for p in PROCESSES[process_index + 1:]:
                p_end_expression = get_end_expression(list_ends, p)
                if p_end_expression:
                    end_expressions.append(p_end_expression)
        if end_expressions:
            if expression:
                end_expressions.append(expression)
            if len(end_expressions) == 1:
                expression = end_expressions[0]
            else:
                expression = and_join(end_expressions)
    return expression


def get_end_expression(processed_nodes, process=None):
    end_node = get_last_end_node(processed_nodes, process)
    if end_node:
        return TriccOperation(TriccOperator.ISNOTTRUE, [end_node])


def export_proposed_diags(activity, diags=None, **kwargs):
    if diags is None:
        diags = []
    for node in activity.nodes.values():
        if isinstance(node, TriccNodeActivity):
            diags = export_proposed_diags(node, diags, **kwargs)
        if isinstance(node, TriccNodeProposedDiagnosis):
            if node.last is not False and not any([diag.name == node.name for diag in diags]):
                diags.append(node)
    return diags

def export_diags(activity, diags=None, **kwargs):
    if diags is None:
        diags = []
    for node in activity.nodes.values():
        if isinstance(node, TriccNodeActivity):
            diags = export_diags(node, diags, **kwargs)
        if isinstance(node, TriccNodeDiagnosis):
            diags.append(node)
    return diags

def get_accept_diagnostic_node(code, display, severity, priority, activity):
    node = TriccNodeAcceptDiagnostic(
        id=generate_id("pre_final." + code),
        name="pre_final." + code,
        label=display,
        list_name="acc_rej",
        activity=activity,
        group=activity,
        severity=severity,
        priority=priority,
    )
    node.options = get_select_accept_reject_options(node, node.activity)
    return node


def get_diagnostic_node(code, display, severity, priority, activity, option):
    node = TriccNodeCalculate(
        id=generate_id("final." + code),
        name="final." + code,
        label=display,
        activity=activity,
        group=activity,
        priority=priority,
        expression_reference=or_join(
            [
                TriccOperation(TriccOperator.ISTRUE, [TriccReference("pre_final." + code)]),
                TriccOperation(TriccOperator.SELECTED, [TriccReference("tricc.manual.diag"), option]),
            ]
        ),
    )
    return node


def get_select_accept_reject_options(node, group):
    yes = TriccNodeSelectOption(
        id=generate_id(f"accept{node.id}"),
        name=f"{TRICC_TRUE_VALUE}",
        label="Accept",
        select=node,
        group=group,
        list_name=node.list_name,
    )
    no = TriccNodeSelectOption(
        id=generate_id(f"reject{node.id}"),
        name=f"{TRICC_FALSE_VALUE}",
        label="Reject",
        select=node,
        group=group,
        list_name=node.list_name,
    )
    return {0: yes, 1: no}


def create_determine_diagnosis_activity(diags):
    start = TriccNodeMainStart(
        id=generate_id("start.determine-diagnosis"), name="start.determine-diagnosis", process="determine-diagnosis"
    )

    activity = TriccNodeActivity(
        id=generate_id("activity-determine-diagnosis"),
        name="determine-diagnosis",
        label="Classifications",
        root=start,
    )

    start.activity = activity
    start.group = activity
    diags_conf = []
    diags_calc = []
    end = TriccNodeActivityEnd(
        id=generate_id("end.determine-diagnosis"),
        name="end.determine-diagnosis",
        activity=activity,
        group=activity,
    )
    activity.nodes[end.id] = end

    f = TriccNodeSelectMultiple(
        name="tricc.manual.diag",
        label="Add classifications",
        list_name="manual_diag",
        id=generate_id("tricc.manual.diag"),
        activity=activity,
        group=activity,
        required=TriccStatic(False),
    )
    options = []
    for proposed in diags:
        option = TriccNodeSelectOption(
            id=generate_id(proposed.name),
            name=proposed.name,
            label=proposed.label,
            list_name=f.list_name,
            activity=activity,
            group=activity,
            relevance=proposed.activity.applicability,
            select=f,
        )
        options.append(option)
        d = get_accept_diagnostic_node(proposed.name, proposed.label, proposed.severity, proposed.priority, activity)
        c = get_diagnostic_node(proposed.name, proposed.label, proposed.severity, proposed.priority, activity, option)
        diags_conf.append(d)
        diags_calc.append(c)
        r = TriccNodeRhombus(
            path=start,
            id=generate_id(f"proposed-rhombus{proposed.id}"),
            expression_reference=TriccOperation(TriccOperator.ISTRUE, [TriccReference(proposed.name)]),
            reference=[TriccReference(proposed.name)],
            activity=activity,
            priority=proposed.priority,
            group=activity,
        )
        activity.calculates.append(r)
        activity.calculates.append(c)
        set_prev_next_node(r, d, edge_only=False)
        #set_prev_next_node(d, end, edge_only=False)
        

        activity.nodes[d.options[0].id] = d.options[0]
        activity.nodes[d.options[1].id] = d.options[1]
        activity.nodes[d.id] = d
        activity.nodes[r.id] = r
        activity.nodes[c.id] = c
        activity.nodes[f.id] = f

    # fallback
    wait1 = get_activity_wait([activity.root], diags_conf, [f], edge_only=False)
    wait2 = get_activity_wait([activity.root], diags_calc, [end], edge_only=False)
    activity.nodes[wait1.id] = wait1
    activity.nodes[wait2.id] = wait2
    f.options = dict(zip(range(0, len(options)), options))
    activity.nodes[f.id] = f
    set_prev_next_node(f, end, edge_only=False)

    return activity


def get_prev_node_expression(node, activity, processed_nodes, get_overall_exp=False, excluded_name=None, process=None):
    expression = None
    sub = None
    if node is None:
        pass
    # when getting the prev node, we calculate the
    if hasattr(node, "expression_inputs") and len(node.expression_inputs) > 0:
        expression_inputs = node.expression_inputs
        expression_inputs = clean_or_list(expression_inputs)
    else:
        expression_inputs = []
    prev_activities = {getattr(node.activity, "id", None): []}
    # sorting prev_nodes per activity
   
    for prev_node in node.prev_nodes:
        if prev_node.activity.id not in prev_activities:
            prev_activities[prev_node.activity.id] = []
        if isinstance(prev_node, TriccNodeActivity):
            for a_prev_node in prev_node.prev_nodes:
                # if we share the calling contect of the activity
                if a_prev_node.activity == node.activity:
                    prev_activities[node.activity.id].append(a_prev_node)
        prev_activities[prev_node.activity.id].append(prev_node)
    # get the or_list expression of all the node per activity
    for act_id in prev_activities:
        act_expression_inputs = []
        none_sequence_defined_prev_node = len(node.prev_nodes) == 0
        for prev_node in prev_activities[act_id]:
            none_sequence_defined_prev_node = none_sequence_defined_prev_node and not prev_node.is_sequence_defined
            if (
                excluded_name is None
                or prev_node != excluded_name
                or (
                    # or isinstance(prev_node, TriccNodeActivityEnd):
                    isinstance(excluded_name, str)
                    and hasattr(prev_node, "name")
                    and prev_node.name != excluded_name
                )
            ):
                # the rhombus should calculate only reference
                # expression from one prev node
                sub = get_node_expression(
                    prev_node,
                    processed_nodes=processed_nodes,
                    get_overall_exp=get_overall_exp,
                    is_prev=True,
                    process=process,
                ) or TriccStatic(True)
                # if it is an activity or overall then we add the sub to act expression 
                # else we update directly the node releavance subs
                if node.activity.id != act_id or get_overall_exp:
                    add_sub_expression(act_expression_inputs, sub)
                else:
                    add_sub_expression(expression_inputs, sub)
        # if cur prev node part of prev act elvaluated have some relevance we make an AND with prev act relevance
        if act_expression_inputs:
            act_sub = or_join(act_expression_inputs)
            # if there is condition fallback on the calling activity condition
            if prev_node.activity.relevance and prev_node.activity.relevance != TriccStatic(True):
                act_relevance = TriccOperation(TriccOperator.ISTRUE, [prev_node.activity.root])
            else:
                act_relevance = TriccStatic(True)
            # get_node_expression(
            #         prev_node.activity,
            #         processed_nodes=processed_nodes,
            #         get_overall_exp=get_overall_exp,
            #         is_prev=True,
            #         negate=False,
            #         process=process,
            #     )
            if act_sub == TriccStatic(True):
                act_sub = act_relevance
            elif act_relevance != TriccStatic(True) and none_sequence_defined_prev_node:
                # For nodes with is_sequence_defined = False, AND the activity relevance with the prev expression
                # activity_relevance = get_node_expression(
                #     prev_node.activity,
                #     processed_nodes=processed_nodes,
                #     get_overall_exp=get_overall_exp,
                #     is_prev=True,
                #     negate=False,
                #     process=process,
                # )
                act_sub = and_join([
                    TriccOperation(
                        TriccOperator.ISTRUE,
                        [prev_node.activity.root]
                    ),
                    act_sub
                ])
            add_sub_expression(expression_inputs, act_sub)
            # avoid void is there is not conditions to avoid looping too much itme
    # expression_inputs = clean_or_list(
    #     [
    #         get_tricc_operation_operand(e)
    #         if isinstance(expression, TriccOperation)
    #         else e
    #         for e in expression_inputs])

    if expression_inputs:
        expression = or_join(expression_inputs)
        # if isinstance(node,  TriccNodeExclusive):
        #    expression =  TRICC_NEGATE.format(expression)
    # only used for activityStart
    else:
        expression = TriccStatic(True)
    return expression


def get_activity_end_terms(node, processed_nodes, process=None):
    end_nodes = node.get_end_nodes()
    expression_inputs = []
    for end_node in end_nodes:
        add_sub_expression(
            expression_inputs,
            get_node_expression(
                end_node, processed_nodes=processed_nodes, get_overall_exp=False, is_prev=True, process=process
            ),
        )

    return or_join(expression_inputs)

def _cast_number(term):
    if isinstance(term, TriccOperation) and term.operator in (TriccOperator.CAST_NUMBER, TriccOperator.CAST_INTEGER):
        return term
    return TriccOperation(TriccOperator.CAST_NUMBER, [term])

def get_count_terms(node, processed_nodes, get_overall_exp, negate=False, process=None):
    terms = []

    for prev_node in node.prev_nodes:
        term = get_count_terms_details(prev_node, processed_nodes, get_overall_exp, negate, process)
        if term:
            terms.append(term)
    if len(terms) == 1:
        return _cast_number(terms[0])
    elif len(terms) > 0: 
        return TriccOperation(TriccOperator.PLUS, [_cast_number(term) for term in terms])


def get_none_option(node):
    if hasattr(node, "options"):
        for opt in node.options.values():
            if opt.name == "opt_none" or opt.is_none == True:
                return opt
    return None


def get_count_terms_details(prev_node, processed_nodes, get_overall_exp, negate=False, process=None):
    opt_none = get_none_option(prev_node)
    if opt_none:
        if isinstance(opt_none, str):
            operation_none = TriccOperation(TriccOperator.SELECTED, [prev_node, TriccStatic(opt_none)])
        elif issubclass(opt_none.__class__, TriccBaseModel):
            operation_none = TriccOperation(TriccOperator.SELECTED, [prev_node, opt_none])
        else:
            logger.critical(f"unexpected none option value {opt_none}")
    else:
        operation_none = TriccOperation(TriccOperator.SELECTED, [prev_node, TriccStatic("opt_none")])
    if isinstance(prev_node, TriccNodeSelectYesNo):
        return TriccOperation(TriccOperator.SELECTED, [prev_node, prev_node.options[0]])
    elif issubclass(prev_node.__class__, TriccNodeSelect):
        if negate:
            return
            # terms.append(TRICC_SELECT_MULTIPLE_CALC_NONE_EXPRESSION.format(get_export_name(prev_node)))
        else:
            return TriccOperation(
                TriccOperator.MINUS,
                [
                    TriccOperation(TriccOperator.COUNT, [prev_node]),
                    TriccOperation(TriccOperator.CAST_NUMBER, [operation_none]),
                ],
            )
            # terms.append(TRICC_SELECT_MULTIPLE_CALC_EXPRESSION.format(get_export_name(prev_node)))
    elif isinstance(prev_node, (TriccNodeSelectNotAvailable)):
        return TriccOperation(TriccOperator.SELECTED, [prev_node, TriccStatic("1")])
        # terms.append(TRICC_SELECTED_EXPRESSION.format(get_export_name(prev_node), '1'))
    elif isinstance(prev_node, TriccNodeSelectOption):
        return get_selected_option_expression(prev_node, negate)
    else:
        if negate:
            return TriccOperation(
                TriccOperator.CAST_NUMBER,
                [
                    TriccOperation(
                        TriccOperator.NATIVE,
                        [
                            TriccOperation(
                                TriccOperator.CAST_NUMBER,
                                [
                                    get_node_expression(
                                        prev_node,
                                        processed_nodes=processed_nodes,
                                        get_overall_exp=get_overall_exp,
                                        is_prev=True,
                                        process=process,
                                    )
                                ],
                            ),
                            TriccStatic("0"),
                        ],
                    )
                ],
            )

        else:
            return TriccOperation(
                TriccOperator.CAST_NUMBER,
                [
                    get_node_expression(
                        prev_node,
                        processed_nodes=processed_nodes,
                        get_overall_exp=get_overall_exp,
                        is_prev=True,
                        process=process
                    )
                ],
            )


def get_add_terms(node, processed_nodes, get_overall_exp=False, negate=False, process=None):
    if negate:
        logger.warning("negate not supported for Add node {}".format(node.get_name()))
    terms = []
    for prev_node in node.prev_nodes:
        if issubclass(prev_node, TriccNodeNumber) or isinstance(node, TriccNodeCount):
            terms.append(TriccOperation(TriccOperator.COALESCE, [prev_node, TriccStatic(0)]))
        else:
            terms.append(
                TriccOperation(
                    TriccOperator.CAST_NUMBER,
                    [
                        get_node_expression(
                            prev_node,
                            processed_nodes=processed_nodes,
                            get_overall_exp=get_overall_exp,
                            is_prev=True,
                            process=process,
                        )
                    ],
                )
            )
    if len(terms) > 0:
        operation = terms[0]
        if len(terms) > 1:
            for term in terms[1:]:
                operation = TriccOperation(TriccOperator.ADD, [operation, term])
        return operation


def get_rhombus_terms(node, processed_nodes, get_overall_exp=False, negate=False, process=None):
    expression = None
    left_term = None
    if node.reference is not None:
        if isinstance(node.reference, set):
            node.reference = list(node.reference)
        # calcualte the expression only for select muzltiple and fake calculate
        if issubclass(node.reference.__class__, (list, OrderedSet)):
            if node.expression_reference is None and len(node.reference) == 1:
                ref = node.reference[0]
                if issubclass(ref.__class__, TriccNodeBaseModel):
                    if isinstance(ref, TriccNodeActivity):
                        expression = get_activity_end_terms(ref, processed_nodes, process=process)
                    elif issubclass(ref.__class__, TriccNodeFakeCalculateBase):
                        expression = get_node_expression(
                            ref, processed_nodes=processed_nodes, get_overall_exp=True, is_prev=True, process=process
                        )
                    else:
                        expression = ref
                elif issubclass(ref.__class__, TriccReference):
                    expression = ref
                else:
                    logger.critical(
                        "reference {0} was not found in the previous nodes of node {1}".format(
                            node.reference, node.get_name()
                        )
                    )
                    exit(1)
            elif node.expression_reference is not None and node.expression_reference != "":
                if isinstance(node.expression_reference, (TriccOperation, TriccReference, TriccStatic)):
                    return node.expression_reference
                elif isinstance(node.expression_reference, str):
                    expression = node.expression_reference.format(*get_list_names(node.reference))
                else:
                    logger.critical(
                        "expression_reference {0} unsuported type {1}".format(
                            node.expression_reference, node.expression_reference.__class__.__name__
                        )
                    )
                    exit(1)

            else:
                logger.warning("missing expression for node {}".format(node.get_name()))
        else:
            logger.critical("reference {0} is not a list {1}".format(node.reference, node.get_name()))
            exit(1)
    else:
        logger.critical("reference empty for Rhombis {}".format(node.get_name()))
        exit(1)

    if expression is not None:
        if isinstance(expression, (TriccOperation, TriccStatic)):
            return expression
        elif issubclass(expression.__class__, TriccNodeCalculateBase):
            return TriccOperation(
                TriccOperator.CAST_NUMBER,
                [
                    get_node_expression(
                        expression,
                        processed_nodes=processed_nodes,
                        get_overall_exp=get_overall_exp,
                        is_prev=True,
                        process=process
                    )
                ],
            )
        elif issubclass(expression.__class__, (TriccOperation)):
            return expression
        elif issubclass(expression.__class__, (TriccNodeDisplayModel, TriccReference)):
            return TriccOperation(TriccOperator.ISTRUE, [expression])
        else:
            if left_term is not None and re.search(" (+)|(-)|(or)|(and) ", expression):
                expression = "({0}){1}".format(expression, left_term)
            else:
                expression = "{0}{1}".format(expression, left_term)
    else:
        logger.critical(
            "Rhombus reference was not found for node {}, reference {}".format(node.get_name(), node.reference)
        )
        exit(1)

    return expression


def _get_factor_path_condition(path, processed_nodes, get_overall_exp=False, process=None):
    """Boolean condition for whether a factor node's path branch was taken."""
    if isinstance(path, TriccNodeRhombus):
        return get_rhombus_terms(path, processed_nodes, get_overall_exp=get_overall_exp, process=process)
    if isinstance(path, TriccNodeSelectYesNo):
        yes_option = next(
            (opt for opt in path.options.values() if str(opt.label).lower() in ("yes", "oui")),
            next(iter(path.options.values()), None),
        )
        if yes_option:
            return TriccOperation(TriccOperator.SELECTED, [path, yes_option])
    if issubclass(path.__class__, TriccNodeSelect):
        return TriccOperation(TriccOperator.ISTRUE, [path])
    if issubclass(path.__class__, TriccNodeCalculateBase):
        return get_node_expression(
            path,
            processed_nodes=processed_nodes,
            get_overall_exp=get_overall_exp,
            is_prev=True,
            process=process,
        )
    return TriccOperation(TriccOperator.ISTRUE, [path])


def get_factor_terms(node, processed_nodes, get_overall_exp=False, negate=False, process=None):
    """Return ``if path then factor else 0`` for sequence scoring nodes."""
    if node.path is None:
        if len(node.prev_nodes) == 1:
            node.path = list(node.prev_nodes)[0]
        elif len(node.prev_nodes) > 1:
            logger.critical(f"missing path for Factor {node.get_name()}")
            exit(1)

    factor_value = node.reference
    if isinstance(factor_value, list) and factor_value:
        factor_value = factor_value[0]
    if not isinstance(factor_value, TriccStatic):
        factor_value = TriccStatic(float(factor_value))

    path_condition = _get_factor_path_condition(
        node.path, processed_nodes, get_overall_exp=get_overall_exp, process=process
    )
    if path_condition is None:
        path_condition = TriccStatic(False)

    if negate:
        path_condition = not_clean(path_condition)

    scored = TriccOperation(TriccOperator.IF, [path_condition, factor_value, TriccStatic(0)])
    return TriccOperation(TriccOperator.CAST_NUMBER, [scored])


# function that generate the calculation terms return by calculate node
# @param node calculate node to assess
# @param processed_nodes list of node already processed, importnat because only processed node could be use
# @param get_overall_exp used when this funciton is called in the evaluation of another calculate
# @param negate use to retriece the negation of a calculation


def get_calculation_terms(node, processed_nodes, get_overall_exp=False, negate=False, process=None):
    # returns something directly only if the negate is managed
    expression = None
    if isinstance(node, TriccNodeAdd):
        return get_add_terms(node, False, negate, process=process)
    elif isinstance(node, TriccNodeCount):
        return get_count_terms(node, False, negate, process=process)
    elif isinstance(node, TriccNodeRhombus):
        return get_rhombus_terms(
            node, processed_nodes=processed_nodes, get_overall_exp=get_overall_exp, negate=negate, process=process
        )
    elif isinstance(node, TriccNodeFactor):
        return get_factor_terms(
            node, processed_nodes=processed_nodes, get_overall_exp=get_overall_exp, negate=negate, process=process
        )
    elif isinstance(node, (TriccNodeWait)):
        # just use to force order of question
        expression = None
    # in case of calulate expression evaluation, we need to get the relevance of the activity
    # because calculate are not the the activity group
    elif isinstance(node, (TriccNodeActivityStart)) and get_overall_exp:
        expression = get_prev_node_expression(
            node.activity,
            node.activity,
            processed_nodes=processed_nodes,
            get_overall_exp=get_overall_exp,
            negate=negate,
            process=process,
        )
    elif isinstance(node, (TriccNodeActivityStart, TriccNodeActivityEnd)):
        # the group have the relevance for the activity, not needed to replicate it
        expression = None
    elif isinstance(node, TriccNodeExclusive):
        if len(node.prev_nodes) == 1:
            iterator = iter(node.prev_nodes)
            node_to_negate = next(iterator)
            if isinstance(node_to_negate, TriccNodeExclusive):
                logger.critical("2 exclusives cannot be on a row")
                exit(1)
            elif issubclass(node_to_negate.__class__, TriccNodeCalculateBase):
                return get_node_expression(
                    node_to_negate,
                    processed_nodes=processed_nodes,
                    get_overall_exp=get_overall_exp,
                    is_prev=True,
                    negate=True,
                    process=process,
                )
            elif isinstance(node_to_negate, TriccNodeActivity):
                return get_node_expression(
                    node_to_negate,
                    processed_nodes=processed_nodes,
                    get_overall_exp=get_overall_exp,
                    is_prev=True,
                    negate=True,
                    process=process,
                )
            else:
                logger.critical(
                    f"exclusive node {node.get_name()}\
                    does not depend of a calculate but on\
                        {node_to_negate.__class__}::{node_to_negate.get_name()}"
                )

        else:
            logger.critical("exclusive node {} has no ou too much parent".format(node.get_name()))

    if isinstance(node.expression_reference, (TriccOperation, TriccStatic)):
        expression = node.expression_reference
    if isinstance(node.expression, (TriccOperation, TriccStatic)):
        expression = node.expression
    elif expression is None:
        expression = get_prev_node_expression(
            node, node.activity, processed_nodes=processed_nodes, get_overall_exp=get_overall_exp, process=process
        )

    # manage the generic negation
    if negate:

        return negate_term(expression)
    else:
        return expression


# Function that add element to array is not None or ''


def add_sub_expression(array, sub):
    if isinstance(sub, (TriccOperation, TriccStatic)):
        not_sub = negate_term(sub)
        if not_sub in array:
            # avoid having 2 conditions that are complete opposites
            array.remove(not_sub)
            array.append(TriccStatic(True))
        else:
            array.append(sub)
    else:
        pass
    # elif sub is None:
    #     array.append(TriccStatic(True))

    # function that negate terms


# @param expression to negate


def negate_term(expression):

    return not_clean(expression)


# if the node is "required" then we can take the fact that it has value for the next elements
def get_required_node_expression(node):
    return TriccOperation(operator=TriccOperator.EXISTS, reference=[node])


# Get a selected option
def get_selected_option_expression(option_node, negate):
    if isinstance(option_node.select, TriccNodeSelectOne):
        return get_selected_option_expression_single(option_node, negate)
    else:
        return get_selected_option_expression_multiple(option_node, negate)


def get_selected_option_expression_single(option_node, negate):

    if not negate:
        return TriccOperation(TriccOperator.EQUAL, [option_node.select, option_node])


def get_selected_option_expression_multiple(option_node, negate):

    selected = TriccOperation(TriccOperator.SELECTED, [option_node.select, option_node])

    if negate:
        return and_join([
                TriccOperation(operator=TriccOperator.NOT, resource=[selected]),
                TriccOperation(operator=TriccOperator.ISNOTNULL, resource=[option_node.select]),
            ])

    else:
        return selected


def generate_calculate(node, processed_nodes, **kwargs):
    # For calculations, set calculate in questionOptions
    # Check if node is ready to be processed (similar to XLS form strategy)
    if not is_ready_to_process(node, processed_nodes, strict=True):
        return False

    # Process references to ensure dependencies are handled
    if not process_reference(
        node, processed_nodes, {}, replace_reference=True, codesystems=kwargs.get("codesystems", None)
    ):
        return False

    if node not in processed_nodes:
        if kwargs.get("warn", False):
            logger.debug("generation of calculate for node {}".format(node.get_name()))

        # Set is_sequence_defined for calculate nodes based on dependencies
        if issubclass(node.__class__, TriccNodeCalculateBase):
            # Calculate node is sequence defined if ALL prev_nodes have is_sequence_defined = True
            node.is_sequence_defined = all(prev_node.is_sequence_defined for prev_node in node.prev_nodes)

        if isinstance(node, TriccNodePopulate):
            from tricc_oo.converters.fhir.populate_helper import resolve_populate_reference

            if node.expression is None and node.expression_reference is None:
                node.expression_reference = TriccStatic(resolve_populate_reference(node))
        elif (
            hasattr(node, "expression")
            and (node.expression is None)
            and issubclass(node.__class__, TriccNodeCalculateBase)
        ):
            node.expression = get_node_expressions(
                node, processed_nodes, process=kwargs.get("process", "main ")
            )
            # continue walk
        if issubclass(
            node.__class__,
            (
                TriccNodeDisplayModel,
                TriccNodeDisplayCalculateBase,
                TriccNodeEnd,
            ),
        ):
            set_last_version_false(node, processed_nodes)
    return True


def generate_base(node, processed_nodes, **kwargs):
    # Generate question for OpenMRS O3 schema
    # Handle activity nodes by processing their inner content
    # Check if node is ready to be processed (similar to XLS form strategy)
    if not is_ready_to_process(node, processed_nodes, strict=False):
        return False

    # Process references to ensure dependencies are handled
    if not process_reference(
        node, processed_nodes, {}, replace_reference=False, codesystems=kwargs.get("codesystems", None)
    ):
        return False
    if node not in processed_nodes:
        if issubclass(node.__class__, TriccRhombusMixIn) and isinstance(node.reference, str):
            logger.warning("node {} still using the reference string".format(node.get_name()))
        if issubclass(node.__class__, TriccNodeInputModel):
            # we don't overright if define in the diagram
            if node.constraint is None:
                if isinstance(node, TriccNodeSelectMultiple):
                    none_opt = get_none_option(node)
                    if none_opt:
                        node.constraint = or_join(
                            [
                                TriccOperation(
                                    TriccOperator.EQUAL,
                                    [TriccStatic("$this"), none_opt],
                                ),
                                TriccOperation(
                                    TriccOperator.NOT,
                                    [
                                        TriccOperation(
                                            TriccOperator.SELECTED,
                                            [TriccStatic("$this"), none_opt],
                                        )
                                    ],
                                ),
                            ]
                        )  # '.=\'opt_none\' or not(selected(.,\'opt_none\'))'
                        node.constraint_message = "**None** cannot be selected together with choice."
                elif node.tricc_type in (
                    TriccNodeType.integer,
                    TriccNodeType.decimal,
                ):
                    constraints = []
                    constraints_min = ""
                    constraints_max = ""
                    if node.min is not None and node.min != "":
                        node.min = float(node.min)
                        if int(node.min) == node.min:
                            node.min = int(node.min)
                        constraints.append(
                            TriccOperation(TriccOperator.MORE_OR_EQUAL, [TriccStatic("$this"), TriccStatic(node.min)])
                        )
                        constraints_min = "The minimum value is {0}.".format(node.min)
                    if node.max is not None and node.max != "":
                        node.max = float(node.max)
                        if int(node.max) == node.max:
                            node.max = int(node.max)
                        constraints.append(
                            TriccOperation(TriccOperator.LESS_OR_EQUAL, [TriccStatic("$this"), TriccStatic(node.max)])
                        )
                        constraints_max = "The maximum value is {0}.".format(node.max)
                    if len(constraints) > 1:
                        node.constraint = and_join(constraints)
                        node.constraint_message = (constraints_min + " " + constraints_max).strip()
                    elif len(constraints) == 1:
                        node.constraint = constraints[0]
                        node.constraint_message = (constraints_min + " " + constraints_max).strip()
        # continue walk
        return True
    return False

def get_process(node) -> str | None:

    """Walk the TRICC graph upward to find the cpg-common-process name for a node.
     Rules (per FHIRcore.md v4 spec):
     1. If the node is a ``TriccNodeMainStart`` → return ``node.process``.
     2. If the node's activity root is a ``TriccNodeMainStart`` → return that root's process.
     3. Otherwise recurse on the node's activity (which itself has prev_nodes / a root).
    
     Args:

     node: Any TRICC node (``TriccNodeBaseModel`` subclass).

     Returns:

     The cpg-common-process string (e.g. ``"registration"``) or ``None`` if not found.

    """
    if node is None:
        return None
     # Rule 1: node itself is the main start
    if isinstance(node, TriccNodeMainStart):
        return getattr(node, "process", None)
    # Rule 2: node's activity root is the main start
    activity = getattr(node, "activity", None)
    if activity is not None:
        root = getattr(activity, "root", None)
        if isinstance(root, TriccNodeMainStart):
            return getattr(root, "process", None)
        # Rule 3: recurse on the activity itself (which may have its own activity/root)
        if activity is not node:
            return get_process(activity)
    # Fallback: try prev_nodes
    for prev in getattr(node, "prev_nodes", []):
        result = get_process(prev)
        if result is not None:
            return result
    return None