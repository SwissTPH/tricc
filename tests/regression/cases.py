"""Regression cases: every fixture in the repo, built with every main output strategy.

Extra real-life projects (folders holding a ``tricc.yaml``) can be added without
committing them: list them in ``TRICC_REGRESSION_DIRS`` (``os.pathsep``-separated).
Their baselines are kept outside the repo, in ``TRICC_REGRESSION_STORE``
(default ``~/.cache/tricc-regression``), since clinical content is not public.
"""

from __future__ import annotations

import glob
import os
from dataclasses import dataclass
from typing import List, Optional

REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
EXPECTED_DIR = os.path.join(REPO, "tests", "regression", "expected")

OUTPUT_STRATEGIES = ["XLSFormStrategy", "XLSFormCHTStrategy", "FHIRStrategy", "OpenSRPStrategy"]


@dataclass(frozen=True)
class Case:
    id: str
    # "file": one input file through run_one_export; "project": a tricc.yaml folder
    # through run_project_build (its own strategies, interventions and follow-ups).
    kind: str
    input: str
    input_strategy: Optional[str]
    output_strategy: Optional[str]
    expected_dir: str

    @property
    def expected_path(self) -> str:
        return os.path.join(self.expected_dir, f"{self.id}.json.gz")


def _fixture_cases() -> List[Case]:
    cases = []
    inputs = [(p, "DrawioStrategy") for p in sorted(glob.glob(os.path.join(REPO, "tests/data/*.drawio")))]
    inputs += [(p, "YamlStrategy") for p in sorted(glob.glob(os.path.join(REPO, "tests/data/yaml/*.yaml")))]
    for path, input_strategy in inputs:
        stem = os.path.splitext(os.path.basename(path))[0]
        prefix = "drawio" if input_strategy == "DrawioStrategy" else "yaml"
        for output_strategy in OUTPUT_STRATEGIES:
            cases.append(
                Case(
                    id=f"{prefix}__{stem}__{output_strategy}",
                    kind="file",
                    input=os.path.relpath(path, REPO),
                    input_strategy=input_strategy,
                    output_strategy=output_strategy,
                    expected_dir=EXPECTED_DIR,
                )
            )
    return cases


def _project_cases() -> List[Case]:
    raw = os.environ.get("TRICC_REGRESSION_DIRS", "")
    store = os.path.expanduser(os.environ.get("TRICC_REGRESSION_STORE", "~/.cache/tricc-regression"))
    cases = []
    for folder in [p for p in raw.split(os.pathsep) if p.strip()]:
        folder = os.path.abspath(os.path.expanduser(folder))
        name = os.path.basename(folder.rstrip(os.sep)) or "project"
        cases.append(
            Case(
                id=f"project__{name}",
                kind="project",
                input=folder,
                input_strategy=None,
                output_strategy=None,
                expected_dir=store,
            )
        )
    return cases


def all_cases() -> List[Case]:
    return _fixture_cases() + _project_cases()
