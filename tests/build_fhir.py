"""Process drawio file(s) into FHIR Questionnaire output.

Thin wrapper around the strategy pipeline used by tests/build.py, fixed to
DrawioStrategy -> FHIRStrategy so it can be run with just an input and
output path.

Usage:
    python tests/build_fhir.py -i path/to/form.drawio -o path/to/output_dir
    python tests/build_fhir.py -i path/to/drawio_folder -o path/to/output_dir
"""
import getopt
import logging
import os
import sys
from pathlib import Path

from tricc_oo.strategies.registry import get_input_strategy, get_output_strategy
from tricc_oo.models.lang import SingletonLangClass

langs = SingletonLangClass()

logger = logging.getLogger("default")
console = logging.StreamHandler()
console.setLevel(logging.INFO)
console.setFormatter(logging.Formatter("%(asctime)s - %(levelname)s - %(message)s"))
logger.addHandler(console)
logger.setLevel(logging.INFO)

INPUT_STRATEGY = "DrawioStrategy"
OUTPUT_STRATEGY = "OpenSRPStrategy"


def print_help():
    print("-i / --input   drawio file or folder path (MANDATORY)")
    print("-o / --output  output directory (MANDATORY)")
    print("-h / --help    print this menu")


def collect_drawio_files(input_path):
    if os.path.isdir(input_path):
        return sorted(
            os.path.join(input_path, f)
            for f in os.listdir(input_path)
            if f.lower().endswith(".drawio")
        )
    if os.path.isfile(input_path) and input_path.lower().endswith(".drawio"):
        return [input_path]
    return []


def main():
    in_path = None
    out_path = None
    try:
        opts, _ = getopt.getopt(sys.argv[1:], "hi:o:", ["input=", "output=", "help"])
    except getopt.GetoptError:
        print_help()
        sys.exit(1)

    for opt, arg in opts:
        if opt in ("-h", "--help"):
            print_help()
            sys.exit()
        elif opt in ("-i", "--input"):
            in_path = arg
        elif opt in ("-o", "--output"):
            out_path = arg

    if not in_path or not out_path:
        print_help()
        sys.exit(2)

    files = collect_drawio_files(in_path)
    if not files:
        logger.critical(f"No .drawio files found at: {in_path}")
        sys.exit(1)

    out_path = os.path.abspath(out_path)
    Path(out_path).mkdir(parents=True, exist_ok=True)

    file_content = []
    for f in files:
        with open(f, "r", encoding="utf-8") as s:
            file_content.append(s.read())
        logger.info(f"Loaded file: {f}")

    InputStrategyCls = get_input_strategy(INPUT_STRATEGY)
    input_strategy = InputStrategyCls(files)
    logger.info(f"Building graph with {InputStrategyCls.__name__}")
    media_path = os.path.join(out_path, "media-tmp")
    project = input_strategy.execute(file_content, media_path)

    OutputStrategyCls = get_output_strategy(OUTPUT_STRATEGY)
    output_strategy = OutputStrategyCls(project, out_path)
    logger.info(f"Generating FHIR output with {OutputStrategyCls.__name__}")
    output_strategy.execute()

    logger.info(f"Done. FHIR output written to: {out_path}")


if __name__ == "__main__":
    main()
