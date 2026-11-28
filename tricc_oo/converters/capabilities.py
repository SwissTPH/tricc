"""Output capability statements (feature/20261125-output-capabilities.md).

A statement (``statement.json`` of a ``@tricc/capabilities-<strategy>`` package) says what one
output strategy can write: operators (with the contexts where it can), catalogue functions,
retrieval and prefill contexts, data types, features and limits. A child statement
(``extends``) lists only what it adds and removes.

A project lists its loaded statements in ``tricc.yaml`` ``capabilities`` (a copy of each file in
the project folder, checked by ``sha256``). The runner checks the project against every
**active** statement after it is loaded and before the walk (:func:`check_project`).

Codes: ``E_CAPABILITY_FILE``, ``E_CAPABILITY_EXTENDS``, ``W_CAPABILITY_LANG``,
``E_OUTPUT_UNSUPPORTED``, ``W_OUTPUT_LIMIT``, ``W_OUTPUT_NO_STATEMENT``.
"""

from __future__ import annotations

import functools
import hashlib
import json
import logging
import os
import re
from dataclasses import dataclass, field
from typing import Any, Dict, Iterable, List, Optional, Sequence, Set, Tuple

logger = logging.getLogger("default")

#: the JSON Schema shipped with the package (a copy of ``capabilities/statement.schema.json``)
SCHEMA_FILE = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data", "capabilities", "statement.schema.json")

#: statement fields that a child adds to or removes from its parent
SET_FIELDS = ("contexts", "functions", "retrieval_contexts", "populate_contexts", "data_types", "features")

#: operators a call to a decision table becomes (checked as ``decision_table_calls``)
TABLE_OPERATORS = ("DMN", "TUPLE", "ZSCORE", "IZSCORE", "DMN_CALL")

#: node attributes always written in the ``inline`` context by outputs that have one (FHIR:
#: FHIRPath ``enableWhenExpression``); a calculation is written in FHIRPath or CQL as the writer
#: chooses, so it needs the operator in either context; the project libraries' calculates and
#: remote references are written in ``library`` (CQL)
INLINE_ATTRIBUTES = ("relevance", "applicability", "trigger")


class TriccCapabilityError(ValueError):
    """A statement cannot be used (``E_CAPABILITY_FILE``, ``E_CAPABILITY_EXTENDS``), or the
    project uses constructs an active statement does not support (``E_OUTPUT_UNSUPPORTED``)."""

    def __init__(self, code: str, message: str):
        super().__init__(f"{code}: {message}")
        self.code = code
        self.message = message


# ---------------------------------------------------------------- semver


_VERSION = re.compile(r"^\s*v?(\d+)(?:\.(\d+|[xX*]))?(?:\.(\d+|[xX*]))?(?:-[0-9A-Za-z.-]+)?\s*$")


def parse_version(text: str) -> Tuple[int, int, int]:
    """``1.4.0`` -> ``(1, 4, 0)`` (a pre-release suffix is ignored)."""
    match = _VERSION.match(text or "")
    if not match:
        raise ValueError(f"not a version: {text!r}")
    return tuple(int(p) if p and p.isdigit() else 0 for p in match.groups())  # type: ignore[return-value]


def _comparator(version: Tuple[int, int, int], text: str) -> bool:
    text = text.strip()
    if text in ("", "*", "x", "X"):
        return True
    for op in (">=", "<=", ">", "<", "="):
        if text.startswith(op):
            other = parse_version(text[len(op):])
            return {
                ">=": version >= other, "<=": version <= other, ">": version > other, "<": version < other,
                "=": version == other,
            }[op]
    if text[0] in "^~":
        low = parse_version(text[1:])
        if text[0] == "^":
            high = (low[0] + 1, 0, 0) if low[0] else ((0, low[1] + 1, 0) if low[1] else (0, 0, low[2] + 1))
        else:
            high = (low[0], low[1] + 1, 0)
        return low <= version < high
    match = _VERSION.match(text)
    if match and any(p in ("x", "X", "*") or p is None for p in match.groups()[1:]):
        parts = match.groups()
        major = int(parts[0])
        if parts[1] is None or not parts[1].isdigit():
            return version[0] == major
        return version[:2] == (major, int(parts[1]))
    return version == parse_version(text)


def satisfies(version: str, version_range: str) -> bool:
    """Whether ``version`` is in an npm-style range: ``1.2.3``, ``^1.2.0``, ``~1.2.0``, ``1.x``,
    ``>=1.0.0 <2.0.0``, alternatives with ``||``."""
    parsed = parse_version(version)
    return any(
        all(_comparator(parsed, part) for part in alternative.split())
        for alternative in (version_range or "*").split("||")
    )


# ---------------------------------------------------------------- statements


@functools.lru_cache(maxsize=1)
def _schema() -> Dict[str, Any]:
    with open(SCHEMA_FILE, encoding="utf-8") as file:
        return json.load(file)


def validate_statement(data: Any, where: str = "statement") -> None:
    """Check a statement against ``statement.schema.json``.

    Raises:
        TriccCapabilityError: ``E_CAPABILITY_FILE`` naming the first schema error.
    """
    import jsonschema

    validator = jsonschema.Draft202012Validator(_schema())
    errors = sorted(validator.iter_errors(data), key=lambda e: list(e.absolute_path))
    if errors:
        error = errors[0]
        path = "/".join(str(p) for p in error.absolute_path) or "(root)"
        raise TriccCapabilityError("E_CAPABILITY_FILE", f"{where}: {path}: {error.message}")


def sha256_of(path: str) -> str:
    """The sha256 (hex) of a file's bytes."""
    with open(path, "rb") as file:
        return hashlib.sha256(file.read()).hexdigest()


def load_statement_file(path: str, sha256: Optional[str] = None) -> Dict[str, Any]:
    """Read and validate one statement file.

    Args:
        path: The file.
        sha256: The expected checksum (``tricc.yaml``), checked when given.

    Raises:
        TriccCapabilityError: ``E_CAPABILITY_FILE`` (missing, bad JSON, bad checksum, schema).
    """
    if not os.path.isfile(path):
        raise TriccCapabilityError("E_CAPABILITY_FILE", f"{path}: file not found")
    if sha256 and sha256_of(path) != sha256.lower():
        raise TriccCapabilityError("E_CAPABILITY_FILE", f"{path}: sha256 does not match tricc.yaml")
    try:
        with open(path, encoding="utf-8") as file:
            data = json.load(file)
    except ValueError as exc:
        raise TriccCapabilityError("E_CAPABILITY_FILE", f"{path}: not JSON ({exc})") from None
    validate_statement(data, path)
    return data


@dataclass
class ResolvedStatement:
    """A statement with its ``extends`` chain applied."""

    id: str
    version: str
    strategy: str
    lang: str
    chain: List[str] = field(default_factory=list)
    contexts: Set[str] = field(default_factory=set)
    operators: Dict[str, Set[str]] = field(default_factory=dict)
    functions: Set[str] = field(default_factory=set)
    retrieval_contexts: Set[str] = field(default_factory=set)
    populate_contexts: Set[str] = field(default_factory=set)
    data_types: Set[str] = field(default_factory=set)
    features: Set[str] = field(default_factory=set)
    limits: Dict[str, Any] = field(default_factory=dict)

    @property
    def label(self) -> str:
        """``@tricc/capabilities-fhir@1.0.0``."""
        return f"{self.id}@{self.version}"

    def writes(self, operator: str, context: Optional[str] = None) -> bool:
        """Whether the output writes ``operator`` (in ``context`` when given)."""
        contexts = self.operators.get(operator)
        return bool(contexts) and (context is None or context in contexts)

    def context_of(self, attribute: str, in_library: bool = False) -> Optional[str]:
        """The context an expression of a node attribute is written in by this output; None when
        the writer chooses (any context of the operator will do)."""
        if len(self.contexts) == 1:
            return next(iter(self.contexts))
        if in_library or attribute == "remote_reference":
            return "library"
        return "inline" if attribute in INLINE_ATTRIBUTES else None

    def as_dict(self) -> Dict[str, Any]:
        """The resolved statement as plain JSON data (sorted), for comparisons and summaries."""
        return {
            "contexts": sorted(self.contexts),
            "operators": {k: sorted(v) for k, v in sorted(self.operators.items())},
            "functions": sorted(self.functions),
            "retrieval_contexts": sorted(self.retrieval_contexts),
            "populate_contexts": sorted(self.populate_contexts),
            "data_types": sorted(self.data_types),
            "features": sorted(self.features),
            "limits": dict(sorted(self.limits.items())),
        }


def _apply(target: ResolvedStatement, part: Dict[str, Any], remove: bool) -> None:
    for name in SET_FIELDS:
        values = set(part.get(name) or [])
        current = getattr(target, name)
        setattr(target, name, current - values if remove else current | values)
    for operator, contexts in (part.get("operators") or {}).items():
        current = target.operators.get(operator, set())
        updated = current - set(contexts) if remove else current | set(contexts)
        if remove and not contexts:
            updated = set()
        if updated:
            target.operators[operator] = updated
        else:
            target.operators.pop(operator, None)


def resolve_statement(statement_id: str, statements: Dict[str, Dict[str, Any]]) -> ResolvedStatement:
    """Apply the ``extends`` chain of a statement.

    Args:
        statement_id: The package name of the statement to resolve.
        statements: The loaded statements by package name (parents included).

    Raises:
        TriccCapabilityError: ``E_CAPABILITY_EXTENDS`` when a parent is not loaded, its version
            is outside the range, or the chain loops.
    """
    chain: List[Dict[str, Any]] = []
    current = statements[statement_id]
    while True:
        chain.append(current)
        parent = current.get("extends")
        if not parent:
            break
        if parent["package"] in [c["id"] for c in chain]:
            raise TriccCapabilityError("E_CAPABILITY_EXTENDS", f"{statement_id}: extends loops at {parent['package']}")
        loaded = statements.get(parent["package"])
        if loaded is None:
            raise TriccCapabilityError(
                "E_CAPABILITY_EXTENDS",
                f"{current['id']}@{current['version']} extends {parent['package']} {parent['version']}, which is not "
                "loaded in this project",
            )
        if not satisfies(loaded["version"], parent["version"]):
            raise TriccCapabilityError(
                "E_CAPABILITY_EXTENDS",
                f"{current['id']}@{current['version']} extends {parent['package']} {parent['version']}; "
                f"the project has {loaded['version']}",
            )
        current = loaded
    top = chain[0]
    resolved = ResolvedStatement(
        id=top["id"], version=top["version"], strategy=top["strategy"], lang=top["lang"],
        chain=[f"{c['id']}@{c['version']}" for c in chain],
    )
    for statement in reversed(chain):
        if statement.get("extends"):
            _apply(resolved, statement.get("add") or {}, remove=False)
            _apply(resolved, statement.get("remove") or {}, remove=True)
        else:
            _apply(resolved, {k: statement.get(k) for k in SET_FIELDS + ("operators",)}, remove=False)
        resolved.limits.update(statement.get("limits") or {})
    return resolved


def diff_statements(old: ResolvedStatement, new: ResolvedStatement) -> Dict[str, Dict[str, List[str]]]:
    """What changed between two resolved statements: ``{field: {added: [...], removed: [...]}}``."""
    changes: Dict[str, Dict[str, List[str]]] = {}
    before, after = old.as_dict(), new.as_dict()
    for name in ("operators",) + SET_FIELDS:
        a = {f"{k}:{c}" for k, v in before[name].items() for c in v} if name == "operators" else set(before[name])
        b = {f"{k}:{c}" for k, v in after[name].items() for c in v} if name == "operators" else set(after[name])
        if a != b:
            changes[name] = {"added": sorted(b - a), "removed": sorted(a - b)}
    return changes


# ---------------------------------------------------------------- the project's statements


def load_project_statements(project_root: str, entries: Sequence[Any], lang: Optional[str] = None
                            ) -> List[ResolvedStatement]:
    """Load the ``tricc.yaml`` ``capabilities`` entries and resolve the active ones.

    Every entry is loaded (an inactive one may be the parent of an active one); only the active
    ones are returned. Nothing is read from the network.

    Args:
        project_root: The folder of ``tricc.yaml`` (``file`` is relative to it).
        entries: ``TriccCapabilityEntry`` items.
        lang: The ``@tricc/lang`` version in use (default ``tricc_oo/lang/VERSION``).

    Raises:
        TriccCapabilityError: ``E_CAPABILITY_FILE`` or ``E_CAPABILITY_EXTENDS``.
    """
    from tricc_oo.converters.lang import lang_version

    lang = lang or lang_version()
    statements: Dict[str, Dict[str, Any]] = {}
    for entry in entries:
        path = os.path.normpath(os.path.join(project_root, entry.file))
        if os.path.commonpath([os.path.abspath(path), os.path.abspath(project_root)]) != os.path.abspath(project_root):
            raise TriccCapabilityError("E_CAPABILITY_FILE", f"{entry.file}: outside the project folder")
        data = load_statement_file(path, entry.sha256)
        if data["id"] != entry.package or data["version"] != entry.version:
            raise TriccCapabilityError(
                "E_CAPABILITY_FILE",
                f"{entry.file} holds {data['id']}@{data['version']}, tricc.yaml says {entry.package}@{entry.version}",
            )
        statements[entry.package] = data
    resolved = []
    for entry in entries:
        if not entry.active:
            continue
        statement = resolve_statement(entry.package, statements)
        if not satisfies(lang, statement.lang):
            logger.warning(
                f"W_CAPABILITY_LANG: {statement.label} names operators and functions of @tricc/lang "
                f"{statement.lang}; this TRICC uses {lang}"
            )
        resolved.append(statement)
    return resolved


# ---------------------------------------------------------------- the check


@dataclass
class CapabilityIssue:
    """One finding of the check."""

    code: str
    statement: str
    strategy: str
    node: str
    construct: str
    message: str

    def __str__(self) -> str:
        return f"{self.code}: {self.message}"


def _unsupported(statement: ResolvedStatement, node: str, construct: str, what: str) -> CapabilityIssue:
    return CapabilityIssue(
        "E_OUTPUT_UNSUPPORTED", statement.label, statement.strategy, node, construct,
        f"{node} uses {what}, which the {statement.strategy} output ({statement.label}) cannot write",
    )


def _table_rows(project: Any, op: Any) -> Tuple[Optional[str], int]:
    from tricc_oo.models.base import TriccStatic

    refs = list(op.reference or [])
    args = refs[1:] if refs and isinstance(refs[0], TriccStatic) and refs[0].value in ("DMN", "DMNFirst", "DMNList") \
        else refs
    head = args[0] if args else None
    table_id = head.value if isinstance(head, TriccStatic) else None
    table = (getattr(project, "decision_tables", None) or {}).get(table_id) if table_id else None
    return table_id, len(getattr(table, "rules", None) or [])


def _check_expression(statement: ResolvedStatement, project: Any, node_label: str, attribute: str,
                      expr: Any, in_library: bool) -> List[CapabilityIssue]:
    from tricc_oo.models.base import TriccOperator
    from tricc_oo.visitors.expression_checks import catalogue_names, iter_operations, native_name

    issues: List[CapabilityIssue] = []
    context = statement.context_of(attribute, in_library)
    catalogue = catalogue_names()
    for op in iter_operations(expr):
        name = op.operator.name
        if name in TABLE_OPERATORS:
            if "decision_table_calls" in statement.features or op.operator != TriccOperator.DMN:
                continue
            limit = statement.limits.get("inline_decision_table_rows")
            table_id, rows = _table_rows(project, op)
            if limit is not None and rows > limit:
                issues.append(CapabilityIssue(
                    "W_OUTPUT_LIMIT", statement.label, statement.strategy, node_label, f"DMN({table_id})",
                    f"{node_label} calls decision table {table_id!r} ({rows} rows): the {statement.strategy} output "
                    f"writes it inline, over its limit of {limit} rows",
                ))
            continue
        if op.operator == TriccOperator.NATIVE:
            function = native_name(op)
            if function in catalogue and function not in statement.functions:
                issues.append(_unsupported(statement, node_label, function, f"{function}()"))
            continue
        if not statement.writes(name, context):
            where = f" {context}" if context and len(statement.contexts) > 1 else ""
            label = name.replace("_", " ").title().replace(" ", "")
            issues.append(CapabilityIssue(
                "E_OUTPUT_UNSUPPORTED", statement.label, statement.strategy, node_label, name,
                f"{node_label} uses {label}, which the {statement.strategy} output cannot write{where} "
                f"({statement.label})",
            ))
    return issues


def check_project(project: Any, statements: Iterable[ResolvedStatement]) -> List[CapabilityIssue]:
    """Check every expression, decision-table call, retrieval and prefill node against each statement.

    Args:
        project: The loaded project (before the decision-table expansion and the walk).
        statements: The active, resolved statements.

    Returns:
        The issues (``E_OUTPUT_UNSUPPORTED``, ``W_OUTPUT_LIMIT``), one per construct, node and
        statement.
    """
    from tricc_oo.models.base import TriccNodeType
    from tricc_oo.visitors.expression_checks import iter_node_expressions, node_label

    statements = list(statements)
    if not statements:
        return []
    library = {id(n) for n in (getattr(project, "library_calculates", None) or [])}
    expressions = list(iter_node_expressions(project))
    populates = [
        n for n in _project_nodes(project)
        if getattr(n, "tricc_type", None) == TriccNodeType.populate and not hasattr(n, "retrieval")
    ]
    retrievals = _used_retrievals(project)
    issues: List[CapabilityIssue] = []
    for statement in statements:
        seen: Set[Tuple[str, str]] = set()
        for node, attribute, expr in expressions:
            label = node_label(node)
            for issue in _check_expression(statement, project, label, attribute, expr, id(node) in library):
                if (issue.node, issue.construct) not in seen:
                    seen.add((issue.node, issue.construct))
                    issues.append(issue)
        for node in populates:
            context = getattr(node, "context", None) or "patient"
            if context not in statement.populate_contexts:
                issues.append(_unsupported(statement, node_label(node), f"populate:{context}",
                                           f"a prefilled value from the {context} context"))
        for retrieval in retrievals:
            if retrieval.context not in statement.retrieval_contexts:
                issues.append(_unsupported(statement, f"retrieval {retrieval.code}", f"retrieval:{retrieval.context}",
                                           f"a retrieval from the {retrieval.context} context"))
    return issues


def _project_nodes(project: Any) -> List[Any]:
    from tricc_oo.visitors.expression_checks import project_nodes

    return project_nodes(project)


def _used_retrievals(project: Any) -> List[Any]:
    from tricc_oo.converters.retrieval import build_used_retrievals, iter_retrievals

    try:
        build_used_retrievals(project)
    except Exception as exc:  # an unknown #code is reported by the build itself
        logger.debug(f"capability check: retrievals not read ({exc})")
        return []
    return list(iter_retrievals(project))


def check_output_statements(output_strategies: Sequence[str], statements: Sequence[ResolvedStatement]) -> None:
    """``W_OUTPUT_NO_STATEMENT`` for each output to build with no active statement for its strategy."""
    if not statements:
        return
    covered = {s.strategy for s in statements}
    for strategy in output_strategies:
        if strategy not in covered:
            logger.warning(
                f"W_OUTPUT_NO_STATEMENT: {strategy} has no active capability statement; it is built unchecked"
            )


def report_issues(issues: Sequence[CapabilityIssue]) -> None:
    """Log every issue; raise when one is an error.

    Raises:
        TriccCapabilityError: ``E_OUTPUT_UNSUPPORTED`` when any issue is an error.
    """
    errors = [i for i in issues if i.code.startswith("E_")]
    for issue in issues:
        (logger.error if issue.code.startswith("E_") else logger.warning)(str(issue))
    if errors:
        raise TriccCapabilityError(
            "E_OUTPUT_UNSUPPORTED",
            f"{len(errors)} construct(s) not supported by the active capability statements; first: {errors[0].message}",
        )
