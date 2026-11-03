"""Run cases in parallel subprocesses, build baselines, and compare against them.

A baseline is the *envelope* of several runs of the trusted code, each with a different
``PYTHONHASHSEED`` so that str-hash dependent behaviour is sampled too (older exports
were not deterministic: drawio element sets, salted ``hash()``, sets of process names):

* ``required``: items present in every run (multiset intersection)
* ``allowed``:  items present in any run (multiset union)

A later build passes when, for every file, required <= build <= allowed, and every
file present in all baseline runs is still produced.
"""

from __future__ import annotations

import gzip
import json
import os
import subprocess
import sys
import tempfile
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from typing import Dict, List, Optional, Sequence

from tests.regression.cases import REPO, Case

BASELINE_RUNS = int(os.environ.get("TRICC_REGRESSION_RUNS", "3"))


def build(case: Case, seed: Optional[int] = None) -> Dict:
    """Build in a fresh interpreter; ``seed=None`` leaves the hash seed random."""
    env = dict(os.environ)
    env.pop("PYTHONHASHSEED", None)
    if seed is not None:
        env["PYTHONHASHSEED"] = str(seed)
    with tempfile.TemporaryDirectory(prefix="tricc-reg-") as tmp:
        out_dir = os.path.join(tmp, "out")
        result_path = os.path.join(tmp, "result.json")
        proc = subprocess.run(
            [sys.executable, "-m", "tests.regression.build_case", case.id, out_dir, result_path],
            cwd=REPO,
            env=env,
            capture_output=True,
            text=True,
            timeout=900,
        )
        if proc.returncode != 0 or not os.path.exists(result_path):
            lines = [line for line in (proc.stderr + proc.stdout).splitlines() if line.strip()]
            return {"error": "build failed: " + (lines[-1] if lines else f"exit {proc.returncode}")}
        with open(result_path, encoding="utf-8") as f:
            return json.load(f)


def build_many(
    cases: Sequence[Case], seeds: Optional[Sequence[Optional[int]]] = None, workers: int = 0
) -> List[Dict]:
    workers = workers or max(1, (os.cpu_count() or 2) - 1)
    seeds = list(seeds) if seeds is not None else [None] * len(cases)
    with ThreadPoolExecutor(max_workers=workers) as pool:
        return list(pool.map(build, cases, seeds))


def envelope(runs: Sequence[Dict]) -> Dict:
    errors = sorted({r["error"] for r in runs if "error" in r})
    ok = [r["files"] for r in runs if "files" in r]
    if errors and not ok:
        # A case that already fails before any change is recorded as such, so that it
        # is visible rather than silently skipped, and a later fix shows as a diff.
        return {"runs": len(runs), "error": errors[0], "files": {}}
    all_files = sorted(set().union(*[set(f) for f in ok]))
    files = {}
    for name in all_files:
        counters = [Counter(f[name]) for f in ok if name in f]
        required = counters[0].copy()
        allowed = counters[0].copy()
        for c in counters[1:]:
            required &= c
            allowed |= c
        files[name] = {
            "always": len(counters) == len(ok),
            "required": sorted(required.elements()),
            "optional": sorted((allowed - required).elements()),
        }
    out = {"runs": len(runs), "files": files}
    if errors:
        out["flaky_error"] = errors[0]
    return out


def save(case: Case, data: Dict) -> None:
    os.makedirs(case.expected_dir, exist_ok=True)
    payload = json.dumps(data, ensure_ascii=False, indent=0, sort_keys=True).encode("utf-8")
    # mtime=0 keeps the .gz bytes stable when the content is unchanged.
    with open(case.expected_path, "wb") as raw:
        with gzip.GzipFile(fileobj=raw, mode="wb", mtime=0) as f:
            f.write(payload)


def load(case: Case) -> Dict:
    with gzip.open(case.expected_path, "rt", encoding="utf-8") as f:
        return json.load(f)


def compare(expected: Dict, actual: Dict, max_lines: int = 40) -> List[str]:
    problems: List[str] = []
    if "error" in expected:
        if "error" not in actual:
            problems.append(f"baseline failed ({expected['error'].splitlines()[-1]}) but build now succeeds")
        return problems
    if "error" in actual:
        return [actual["error"]]
    got = actual["files"]
    for name, spec in expected["files"].items():
        if name not in got:
            if spec["always"]:
                problems.append(f"missing file {name}")
            continue
        have = Counter(got[name])
        required = Counter(spec["required"])
        allowed = required + Counter(spec["optional"])
        for item in sorted((required - have).elements()):
            problems.append(f"{name}: - {item}")
        for item in sorted((have - allowed).elements()):
            problems.append(f"{name}: + {item}")
    for name in sorted(set(got) - set(expected["files"])):
        problems.append(f"unexpected file {name}")
    if len(problems) > max_lines:
        problems = problems[:max_lines] + [f"... and {len(problems) - max_lines} more"]
    return problems
