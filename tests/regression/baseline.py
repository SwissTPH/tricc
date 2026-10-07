"""(Re)generate regression baselines from the current code.

Run this on the commit you trust *before* changing anything:

    python -m tests.regression.baseline            # all cases
    python -m tests.regression.baseline yaml__     # only case ids containing "yaml__"

Each case is built ``BASELINE_RUNS`` times (``TRICC_REGRESSION_RUNS``, default 3), run i
with ``PYTHONHASHSEED=i``; see ``harness`` for how the runs are combined.
"""

from __future__ import annotations

import sys
import time

from tests.regression.cases import all_cases
from tests.regression.harness import BASELINE_RUNS, build_many, envelope, save


def main(argv) -> int:
    cases = [c for c in all_cases() if not argv or any(a in c.id for a in argv)]
    started = time.time()
    # Run i of every case uses PYTHONHASHSEED=i.
    runs = build_many(
        [c for c in cases for _ in range(BASELINE_RUNS)],
        seeds=[i for _ in cases for i in range(BASELINE_RUNS)],
    )
    unstable = failed = 0
    for i, case in enumerate(cases):
        data = envelope(runs[i * BASELINE_RUNS : (i + 1) * BASELINE_RUNS])
        save(case, data)
        if "error" in data:
            failed += 1
            print(f"FAILS   {case.id}: {data['error'].splitlines()[-1]}")
        elif any(f["optional"] or not f["always"] for f in data["files"].values()) or "flaky_error" in data:
            unstable += 1
            n = sum(len(f["optional"]) for f in data["files"].values())
            print(f"UNSTABLE {case.id}: {n} item(s) vary between runs")
    print(
        f"{len(cases)} baselines written in {time.time() - started:.0f}s "
        f"({unstable} non-deterministic, {failed} already failing)"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
