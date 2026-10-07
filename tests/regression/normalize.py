"""Order-insensitive normalisation of a build output folder.

Existing exports are not byte-deterministic: sibling rows, concepts and JSON list items
can come out in a different order from one run to the next, even with a fixed
``PYTHONHASHSEED``. The regression suite therefore compares *content*, not order:

Every file becomes a sorted list of string *items*:

* ``.xlsx``  -> ``sheet<TAB>row-as-json`` per row (header included)
* ``.json``  -> ``path=value`` per leaf; list indices are dropped, and base64 ``data``
               attachments (FHIR ``Library.content``) are decoded and split into lines
* text       -> one item per non-blank line
* other      -> ``sha256:<hex>``

Build timestamps (``202610061636`` form versions, ISO dates and datetimes) are masked, and
so is the trailing counter of generated XLSForm group/repeat names, which depends on
traversal order (``s_..._1_14`` vs ``s_..._1_15``), and the ``more_info_<n>`` choice-list
counter from ``serializers/xls_form.py`` (``get_more_info_select``), for the same reason.
Set ``TRICC_REGRESSION_NO_COUNTER_MASK=1`` to keep those counters (diagnostics only).

A real regression (a row, attribute, expression or concept that changes or disappears)
still shows up; a pure reordering does not.
"""

from __future__ import annotations

import base64
import binascii
import hashlib
import json
import os
import re
from typing import Any, Dict, Iterator, List

TEXT_EXTS = {".cql", ".map", ".js", ".xml", ".txt", ".csv", ".html", ".md", ".po", ".yaml", ".yml"}
SKIP_DIRS = {"media-tmp", ".tricc-drive-cache"}

_MASKS = [
    (re.compile(r"\b\d{4}-\d{2}-\d{2}[T ]\d{2}:\d{2}(:\d{2}(\.\d+)?)?(Z|[+-]\d{2}:?\d{2})?"), "<DATETIME>"),
    (re.compile(r"\b20\d{2}-\d{2}-\d{2}\b"), "<DATE>"),
    (re.compile(r"\b20\d{2}(0[1-9]|1[0-2])(0[1-9]|[12]\d|3[01])([01]\d|2[0-3])[0-5]\d(\d{2})?\b"), "<TIMESTAMP>"),
]


def _mask(item: str) -> str:
    for pattern, repl in _MASKS:
        item = pattern.sub(repl, item)
    return item


def _decode_attachment(value: str) -> List[str]:
    try:
        raw = base64.b64decode(value, validate=True)
    except (binascii.Error, ValueError):
        return [value]
    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError:
        return ["sha256:" + hashlib.sha256(raw).hexdigest()]
    return [line.rstrip() for line in text.splitlines() if line.strip()]


def _leaves(value: Any, path: str) -> Iterator[str]:
    if isinstance(value, dict):
        for key, child in value.items():
            if key == "data" and isinstance(child, str) and len(child) > 64:
                for line in _decode_attachment(child):
                    yield f"{path}.data>{line}"
                continue
            yield from _leaves(child, f"{path}.{key}")
    elif isinstance(value, list):
        for child in value:
            yield from _leaves(child, f"{path}[]")
    else:
        yield f"{path}={json.dumps(value, ensure_ascii=False)}"


_GROUP_TYPES = {"begin group", "end group", "begin repeat", "end repeat"}
_GROUP_COUNTER = re.compile(r"_\d+(_end)?$")
_MORE_INFO_LIST = re.compile(r"\bmore_info_\d+\b")


def _xlsx(path: str) -> Iterator[str]:
    import pandas as pd

    for name, df in pd.read_excel(path, sheet_name=None, dtype=str).items():
        df = df.fillna("")
        columns = [str(c) for c in df.columns]
        name_col = columns.index("name") if "name" in columns else None
        yield f"{name}\t" + json.dumps(columns, ensure_ascii=False)
        mask_counters = not os.environ.get("TRICC_REGRESSION_NO_COUNTER_MASK")
        for row in df.itertuples(index=False):
            row = list(row)
            if not mask_counters:
                yield f"{name}\t" + json.dumps(row, ensure_ascii=False)
                continue
            if name_col is not None and row and row[0] in _GROUP_TYPES:
                row[name_col] = _GROUP_COUNTER.sub(r"_<N>\1", row[name_col])
            row = [_MORE_INFO_LIST.sub("more_info_<N>", v) for v in row]
            yield f"{name}\t" + json.dumps(row, ensure_ascii=False)


def normalize_file(path: str) -> List[str]:
    ext = os.path.splitext(path)[1].lower()
    if ext == ".xlsx":
        items = list(_xlsx(path))
    elif ext == ".json":
        with open(path, encoding="utf-8") as f:
            items = list(_leaves(json.load(f), ""))
    elif ext in TEXT_EXTS:
        with open(path, encoding="utf-8", errors="replace") as f:
            items = [line.rstrip() for line in f if line.strip()]
    else:
        with open(path, "rb") as f:
            items = ["sha256:" + hashlib.sha256(f.read()).hexdigest()]
    return sorted(_mask(i) for i in items)


def normalize_dir(root: str) -> Dict[str, List[str]]:
    out: Dict[str, List[str]] = {}
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = sorted(d for d in dirnames if d not in SKIP_DIRS)
        for name in sorted(filenames):
            full = os.path.join(dirpath, name)
            rel = os.path.relpath(full, root).replace(os.sep, "/")
            out[rel] = normalize_file(full)
    return out
