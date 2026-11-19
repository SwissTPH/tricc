"""Output regression suite: existing content must keep converting to the same forms.

Opt-in, because it builds every fixture with every main output strategy (a few minutes):

    TRICC_REGRESSION=1 pytest tests/test_regression_outputs.py

Baselines come from ``python -m tests.regression.baseline`` (see ``tests/regression``).
"""

from __future__ import annotations

import os

import pytest

from tests.regression.cases import all_cases
from tests.regression.harness import build_many, compare, load

pytestmark = pytest.mark.skipif(
    not os.environ.get("TRICC_REGRESSION"), reason="set TRICC_REGRESSION=1 to run the output regression suite"
)

CASES = [c for c in all_cases() if os.path.exists(c.expected_path)]


@pytest.fixture(scope="module")
def built():
    # Build everything up front in parallel; each test then only compares.
    return dict(zip([c.id for c in CASES], build_many(CASES)))


@pytest.mark.parametrize("case", CASES, ids=[c.id for c in CASES])
def test_output_matches_baseline(case, built):
    problems = compare(load(case), built[case.id])
    assert not problems, "\n".join(problems)


def test_every_case_has_a_baseline():
    missing = [c.id for c in all_cases() if not os.path.exists(c.expected_path)]
    assert not missing, "no baseline for: " + ", ".join(missing)
