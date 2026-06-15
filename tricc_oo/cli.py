"""
TRICC Command Line Interface.

This module contains the main build/conversion logic so that the package
can be invoked cleanly via `tricc ...` (after proper console_script wiring)
without requiring users to call `python tests/build.py`.

The current `tests/build.py` is a thin wrapper + extended development harness
(Google Drive support, etc.). Over time the goal is to move most logic here.
"""

import logging
import os
import sys
from pathlib import Path
from typing import List, Optional

from tricc_oo.strategies.registry import get_input_strategy, get_output_strategy

logger = logging.getLogger("default")


def run_build(
    input_paths: List[str],
    output_path: str,
    input_strategy: str = "DrawioStrategy",
    output_strategy: str = "XLSFormStrategy",
    form_id: Optional[str] = None,
    debug_level: Optional[str] = None,
    **kwargs,
) -> int:
    """
    Core build/conversion entry point that can be called from the CLI,
    from tests, or programmatically.

    This is the function that should eventually power the `tricc` console script.
    """
    from tricc_oo.models.lang import SingletonLangClass  # local import to avoid heavy side effects at import time

    # Very minimal logging setup (real setup still lives in tests/build.py for now)
    if debug_level:
        # In a real implementation we would call setup_logger here
        pass

    # Collect file contents (simplified version of the logic in build.py)
    file_content: List[str] = []
    files: List[str] = []

    valid_exts = (".drawio", ".yaml", ".yml")

    for current in input_paths:
        current = current.strip()
        if os.path.isdir(current):
            for f in os.listdir(current):
                if f.lower().endswith(valid_exts):
                    files.append(os.path.join(current, f))
        elif os.path.isfile(current) and current.lower().endswith(valid_exts):
            files.append(current)
        else:
            logger.warning(f"Skipping invalid input: {current}")

    for f in files:
        try:
            with open(f, "r", encoding="utf-8") as s:
                file_content.append(s.read())
                logger.info(f"Loaded file: {f}")
        except Exception as e:
            logger.error(f"Error reading file {f}: {e}")

    if not file_content:
        logger.critical("No valid input files found")
        return 2

    # Resolve strategies via the registry (supports both name and direct class)
    InputStrategyCls = get_input_strategy(input_strategy)
    OutputStrategyCls = get_output_strategy(output_strategy)

    logger.info(f"build the graph from strategy {InputStrategyCls.__name__}")

    media_path = os.path.join(output_path, "media-tmp")
    os.makedirs(media_path, exist_ok=True)

    input_strategy_obj = InputStrategyCls(files)
    project = input_strategy_obj.execute(file_content, media_path)

    output_strategy_obj = OutputStrategyCls(project, output_path)
    logger.info(f"Using strategy {OutputStrategyCls.__name__}")

    # The heavy lifting (process_base, process_calculate, process_export, export, validate)
    # is still inside the strategy. We just orchestrate here.
    output = output_strategy_obj.execute()

    logger.info("Conversion completed successfully")
    return 0


def main(argv: Optional[List[str]] = None) -> int:
    """
    Entry point for the `tricc` console script.

    For now this is a placeholder that points people at tests/build.py.
    Once the full argument parsing + Google Drive logic is moved here,
    this will become the real implementation.
    """
    print("The `tricc` CLI is being modernized.")
    print("For the moment please continue using:")
    print("    python tests/build.py -i <input> -o <output> -I <InputStrategy> -O <OutputStrategy>")
    print()
    print("The registry now supports both names and direct class references,")
    print("and YamlStrategy is available for focused testing of transformations.")
    return 0


if __name__ == "__main__":
    sys.exit(main())