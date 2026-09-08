"""
TRICC command-line entry point (``tricc`` console script).

A clinical project lives outside this repository. Put ``tricc.yaml`` next to the
drawings and run from that folder::

    tricc -o ./build

``-i`` defaults to the current working directory. Strategies, interventions, and
image caps come from ``tricc.yaml`` unless ``-I`` / ``-O`` override them.

``python tests/build.py`` remains the debug harness (launch.json matrix).
Google Drive file/folder URLs also belong in ``tricc.yaml`` ``segment:``.
"""

from __future__ import annotations

import argparse
import logging
import os
import sys
from typing import List, Optional

from tricc_oo.runner import run_project_build

logger = logging.getLogger("default")

LEVELS = {
    "d": logging.DEBUG,
    "debug": logging.DEBUG,
    "i": logging.INFO,
    "info": logging.INFO,
    "w": logging.WARNING,
    "warning": logging.WARNING,
}


def _setup_logger(log_file: str, level: int) -> None:
    log = logging.getLogger("default")
    log.setLevel(level)
    formatter = logging.Formatter(
        "[%(asctime)s] {%(pathname)s:%(lineno)d} %(levelname)s - %(message)s"
    )
    file_handler = logging.FileHandler(log_file, mode="w+", encoding="utf-8")
    file_handler.setFormatter(formatter)
    stream_handler = logging.StreamHandler()
    stream_handler.setFormatter(formatter)
    log.handlers.clear()
    log.addHandler(file_handler)
    log.addHandler(stream_handler)


def parse_args(argv: Optional[List[str]] = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="tricc",
        description=(
            "Convert a TRICC project folder (draw.io + optional tricc.yaml) "
            "into XLSForm, CHT, OpenSRP, or other exports."
        ),
    )
    parser.add_argument(
        "-i",
        "--input",
        default=None,
        help="Project folder or file (default: current directory). "
        "Looks for tricc.yaml / tricc.yml here.",
    )
    parser.add_argument(
        "-o",
        "--output",
        default=None,
        help="Output directory (default: ./output next to the project).",
    )
    parser.add_argument(
        "-I",
        dest="input_strategy",
        default=None,
        help="Input strategy name (overrides tricc.yaml input_strategy).",
    )
    parser.add_argument(
        "-O",
        dest="output_strategy",
        default=None,
        help="Output strategy name (replaces tricc.yaml output_strategies).",
    )
    parser.add_argument(
        "-T",
        dest="test_strategy",
        default=None,
        help="Optional test strategy (does not change deployable output).",
    )
    parser.add_argument(
        "-l",
        dest="log_level",
        default="i",
        help="Log level: d/i/w or debug/info/warning (default: i).",
    )
    return parser.parse_args(argv)


def main(argv: Optional[List[str]] = None) -> int:
    args = parse_args(argv)
    in_filepath = os.path.abspath(args.input or os.getcwd())
    if args.output:
        out_path = os.path.abspath(args.output)
    elif os.path.isdir(in_filepath):
        out_path = os.path.join(in_filepath, "output")
    else:
        out_path = os.path.join(os.path.dirname(in_filepath), "output")
    os.makedirs(out_path, exist_ok=True)
    level_key = (args.log_level or "i").lower()
    level = LEVELS.get(level_key, logging.INFO)
    _setup_logger(os.path.join(out_path, "debug.log"), level)
    logger.info("Project: %s", in_filepath)
    logger.info("Output: %s", out_path)
    return run_project_build(
        in_filepath,
        out_path,
        cli_input_strategy=args.input_strategy,
        cli_output_strategy=args.output_strategy,
        test_strategy_name=args.test_strategy,
    )


if __name__ == "__main__":
    sys.exit(main())
