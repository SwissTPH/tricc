# Strategy loading is now done via the registry (much cleaner + supports direct class usage)
from tricc_oo.converters.google_drive import (  # noqa: F401 — re-export for tests/_tmp_fetch_etat.py
    GOOGLE_AUTH_AVAILABLE,
    download_google_drive_file,
    extract_google_drive_file_id,
    extract_google_drive_folder_id,
    is_google_drive_folder_url,
    is_google_drive_url,
    list_google_drive_folder_files,
    resolve_google_drive_source,
)
from tricc_oo.converters.project_config import load_project_config_for_input
from tricc_oo.runner import run_project_build
import getopt
import logging
import os
import sys
import gc
import tempfile
from pathlib import Path

if not GOOGLE_AUTH_AVAILABLE:
    print("Warning: Google API libraries not available. Only direct downloads will work.")

# set up logging to file
from tricc_oo.models.lang import SingletonLangClass

# gettext.bindtextdomain('tricc', './locale/')
# gettext.textdomain('tricc')
langs = SingletonLangClass()

# fr =  gettext.translation('tricc', './locales' , languages=['fr'])
# fr.install()
# en =  gettext.translation('tricc', './locales' , languages=['en'])
# en.install()


# langs.add_trad('fr', fr)
# langs.add_trad('en', en)


# from tricc_oo.serializers.medalcreator import execute


def setup_logger(
    logger_name,
    log_file,
    level=logging.INFO,
    formatting="[%(asctime)s] {%(pathname)s:%(lineno)d} %(levelname)s - %(message)s",
):
    logger = logging.getLogger(logger_name)
    formatter = logging.Formatter(formatting)
    file_handler = logging.FileHandler(log_file, mode="w+")
    file_handler.setFormatter(formatter)
    stream_handler = logging.StreamHandler()
    stream_handler.setFormatter(formatter)

    logger.setLevel(level)
    logger.addHandler(file_handler)


class ColorFormatter(logging.Formatter):
    # Define ANSI escape codes for colors
    grey = "\x1b[38;21m"
    yellow = "\x1b[33;21m"
    red = "\x1b[31;21m"
    bold_red = "\x1b[31;1m"
    reset = "\x1b[0m"
    format = "%(asctime)s - %(name)s - %(levelname)s - %(message)s (%(filename)s:%(lineno)d)"

    # Map log levels to their respective colors
    FORMATS = {
        logging.DEBUG: grey + format + reset,
        logging.INFO: grey + format + reset,
        logging.WARNING: yellow + format + reset,
        logging.ERROR: red + format + reset,
        logging.CRITICAL: bold_red + format + reset,
    }

    def format(self, record):
        # Get the appropriate color format for the log level
        log_fmt = self.FORMATS.get(record.levelno)
        formatter = logging.Formatter(log_fmt)
        return formatter.format(record)


logger = logging.getLogger("default")


# set up logging to console
console = logging.StreamHandler()
console.setLevel(logging.INFO)
# set a format which is simpler for console use
console.setFormatter(ColorFormatter())
# add the handler to the root logger
logging.getLogger("default").addHandler(console)

LEVELS = {
    "d": logging.DEBUG,
    "w": logging.WARNING,
    "i": logging.INFO,
}


def print_help():
    print("-i / --input file path, folder path, or Google Drive file/folder URL (MANDATORY; comma-separated allowed)")
    print("-o / --output xls file ")
    print("-d form_id ")
    print("-s L4 system/strategy (odk, cht, cc)")
    print("-I input strategy (default DrawioStrategy, or tricc.yaml input_strategy)")
    print("-O output strategy (overrides tricc.yaml output_strategies; default XLSFormCHTStrategy)")
    print("Prefer the `tricc` command for local projects:  tricc -i <project> -o <output>")
    print("-T test strategy, runs after the output strategy and adds test material")
    print("     without changing the deployable artifact (e.g. TestSpecStrategy)")
    print("-h / --help print that menu")


def list_local_folder_files(folder_path, valid_exts=(".drawio",)):
    """List input files from a local folder."""
    folder_path = os.path.abspath(folder_path)
    if not folder_path or not os.path.isdir(folder_path):
        return []

    folder_files = []
    for filename in os.listdir(folder_path):
        if filename.lower().endswith(valid_exts):
            folder_files.append(os.path.join(folder_path, filename))
    return sorted(folder_files)


def add_unique_files(files, new_paths):
    """Append file paths that are not already in files (by resolved absolute path)."""
    seen = {os.path.abspath(f) for f in files}
    for path in new_paths:
        abs_path = os.path.abspath(path)
        if abs_path not in seen:
            files.append(path)
            seen.add(abs_path)


if __name__ == "__main__":
    gc.disable()

    system = "odk"
    in_filepath = None
    out_path = None
    form_id = None
    debug_level = None
    trad = False
    download_dir = None
    cli_input_strategy = None
    cli_output_strategy = None
    test_strategy = None
    try:
        opts, args = getopt.getopt(
            sys.argv[1:],
            "hti:o:s:I:O:T:l:d:D:",
            ["input=", "output=", "help", "trads"],
        )
    except getopt.GetoptError:
        print_help()
        sys.exit(1)
    for opt, arg in opts:
        if opt in ("-h", "--help"):
            print_help()
            sys.exit()
        elif opt in ("-i", "--input"):
            in_filepath = arg
        elif opt == "-o":
            out_path = arg
        elif opt == "-I":
            cli_input_strategy = arg
        elif opt == "-O":
            cli_output_strategy = arg
        elif opt == "-T":
            test_strategy = arg
        elif opt == "-d":
            form_id = arg
        elif opt == "-l":
            debug_level = arg
        elif opt in ("-t", "--trads"):
            trad = True
        elif opt == "-D":
            download_dir = arg
    if in_filepath is None:
        print_help()
        sys.exit(2)

    if not download_dir:
        download_dir = out_path
    debug_path = os.fspath(out_path + "/debug.log")
    debug_path = os.path.abspath(debug_path)

    debug_file = Path(debug_path)
    debug_file.parent.mkdir(exist_ok=True, parents=True)
    logfile = open(debug_path, "w")

    debug_file_path = os.path.join(out_path, "debug.log")

    if debug_level is not None:
        setup_logger("default", debug_file_path, LEVELS[debug_level])
    elif "pydevd" in sys.modules:
        setup_logger("default", debug_file_path, logging.INFO)
    else:
        setup_logger("default", debug_file_path, logging.INFO)
    try:
        project_config = load_project_config_for_input(in_filepath)
    except Exception as exc:
        logger.critical(str(exc))
        sys.exit(1)
    files = []
    downloaded_files = []  # Track downloaded files for cleanup

    # Handle comma-separated inputs (files, directories, or Google Drive URLs)
    in_filepath_list = in_filepath.split(",")
    for current_input in in_filepath_list:
        current_input = current_input.strip()

        if is_google_drive_folder_url(current_input) or is_google_drive_url(current_input):
            if project_config.interventions:
                logger.warning(
                    "Ignoring Google Drive -i %s because tricc.yaml lists interventions; "
                    "put Drive URLs in each intervention's segment: list instead",
                    current_input,
                )
                continue
            logger.info("Detected Google Drive URL: %s", current_input)
            try:
                local_paths = resolve_google_drive_source(
                    current_input,
                    tempfile.gettempdir(),
                    valid_exts=(".drawio",),
                )
            except ValueError as exc:
                logger.error("%s", exc)
                sys.exit(1)
            if not local_paths:
                logger.error("No .drawio files downloaded from Google Drive: %s", current_input)
                sys.exit(1)
            downloaded_files.extend(local_paths)
            add_unique_files(files, local_paths)
            logger.info("Downloaded %s Google Drive file(s)", len(local_paths))
        else:
            # Handle local files/directories unless tricc.yaml lists intervention globs.
            if project_config.interventions:
                continue
            valid_exts = (".drawio", ".yaml", ".yml")
            if os.path.isdir(current_input):
                folder_files = list_local_folder_files(current_input, valid_exts=valid_exts)
                if not folder_files:
                    logger.warning(f"No matching files found in folder: {current_input}")
                else:
                    logger.info(f"Found {len(folder_files)} file(s) in folder.")
                    add_unique_files(files, folder_files)
            elif os.path.isfile(current_input) and current_input.lower().endswith(valid_exts):
                add_unique_files(files, [current_input])
            else:
                logger.warning(f"Skipping invalid input (unknown extension): {current_input}")

    exit_code = run_project_build(
        in_filepath,
        out_path,
        cli_input_strategy=cli_input_strategy,
        cli_output_strategy=cli_output_strategy,
        test_strategy_name=test_strategy,
        precollected_files=files,
    )
    if exit_code:
        sys.exit(exit_code)

    # compress the output folder to a zip archieve and place it in the download directory
    # shutil.make_archive(os.path.join(download_dir), "zip", os.path.join(out_path))

    # if trad:
    # langs.to_po_file("./trad.po")

    # Cleanup downloaded temp files
    for temp_file in downloaded_files:
        try:
            if os.path.exists(temp_file):
                os.remove(temp_file)
                logger.info(f"Cleaned up temp file: {temp_file}")
        except Exception as e:
            logger.warning(f"Failed to clean up temp file {temp_file}: {e}")
