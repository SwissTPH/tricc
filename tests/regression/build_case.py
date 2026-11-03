"""Build one regression case in a fresh interpreter and write its normalised output.

Each case runs in its own process so that module-level state left by one build
(caches, registries, mutable defaults) cannot change the next one — the same
isolation the ``tricc`` CLI gets.

    python -m tests.regression.build_case <case-id> <out-dir> <result.json>
"""

from __future__ import annotations

import json
import logging
import os
import sys


def main(argv) -> int:
    case_id, out_dir, result_path = argv
    # Keep ERROR/CRITICAL on stderr so a crash explains itself; the result goes to a
    # file because some loggers write to stdout.
    logging.disable(logging.WARNING)

    from tests.regression.cases import REPO, all_cases
    from tests.regression.normalize import normalize_dir

    case = next(c for c in all_cases() if c.id == case_id)
    os.chdir(REPO)
    if case.kind == "file":
        from tricc_oo.models.project_config import TriccProjectConfig
        from tricc_oo.runner import read_input_file_contents, run_one_export

        files = [case.input]
        run_one_export(
            files,
            read_input_file_contents(files),
            out_dir,
            case.input_strategy,
            case.output_strategy,
            TriccProjectConfig(),
            None,
        )
    else:
        from tricc_oo.runner import run_project_build

        rc = run_project_build(case.input, out_dir)
        if rc != 0:
            print(f"run_project_build exited {rc}", file=sys.stderr)
            return 1
    with open(result_path, "w", encoding="utf-8") as f:
        json.dump({"files": normalize_dir(out_dir)}, f, ensure_ascii=False)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
