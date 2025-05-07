import getopt
import gettext
import logging
import os
import sys
import gc
import shutil
from pathlib import Path

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

from tricc_oo.strategies.input.drawio import DrawioStrategy

# from tricc_oo.serializers.medalcreator import execute

from tricc_oo.strategies.output.xls_form import XLSFormStrategy
from tricc_oo.strategies.output.xlsform_cdss import XLSFormCDSSStrategy
from tricc_oo.strategies.output.xlsform_cht import XLSFormCHTStrategy
from tricc_oo.strategies.output.xlsform_cht_hf import XLSFormCHTHFStrategy
from tricc_oo.strategies.output.spice import SpiceStrategy

def setup_logger(
    logger_name,
    log_file,
    level=logging.INFO,
    formatting="[%(asctime)s] {%(pathname)s:%(lineno)d} %(levelname)s - %(message)s",
):
    l = logging.getLogger(logger_name)
    formatter = logging.Formatter(formatting)
    file_handler = logging.FileHandler(log_file, mode="w+")
    file_handler.setFormatter(formatter)
    stream_handler = logging.StreamHandler()
    stream_handler.setFormatter(formatter)

    l.setLevel(level)
    l.addHandler(file_handler)


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
    print(
        "-i / --input draw.io filepath (MANDATORY) or directory containing drawio files"
    )
    print("-o / --output xls file ")
    print("-d form_id ")
    print("-s L4 system/strategy (odk, cht, cc)")
    print("-h / --help print that menu")


if __name__ == "__main__":
    gc.disable()

    system = "odk"
    in_filepath = None
    out_path = None
    form_id = None
    debug_level = None
    trad = False
    download_dir = None
    input_strategy = "DrawioStrategy"
    output_strategy = "XLSFormStrategy"
    try:
        opts, args = getopt.getopt(
            sys.argv[1:], "hti:o:s:I:O:l:d:D:", ["input=", "output=", "help", "trads"]
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
            input_strategy = arg
        elif opt == "-O":
            output_strategy = arg
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
        setup_logger("default", debug_file_path, logging.DEBUG)
    else:
        setup_logger("default", debug_file_path, logging.INFO)
    file_content = []
    files = []
    in_filepath_list = in_filepath.split(',')
    for in_filepath in in_filepath_list:
        pre, ext = os.path.splitext(in_filepath)

        if out_path is None:
            # if output file path not specified, just chagne the extension
            out_path = os.path.dirname(pre)


        if os.path.isdir(in_filepath):
            files = [
                os.path.join(in_filepath, f)
                for f in os.listdir(in_filepath) 
                if f.endswith(".drawio")
            ]
        elif os.path.isfile(in_filepath) and in_filepath.endswith(".drawio"):
            files = [in_filepath]
            
        for f in files:
            with open(f, 'r') as s:
                content = s.read()
                # present issue with some drawio file that miss the XML header

                file_content.append(content)
    if not file_content:
        logger.critical(f"{in_filepath} is neither a drawio file nor a directory containing drawio files")
        exit(1)


    strategy = globals()[input_strategy](files)
    logger.info(f"build the graph from strategy {input_strategy}")
    media_path = os.path.join(out_path, "media-tmp")
    project = strategy.execute(file_content, media_path)

    strategy = globals()[output_strategy](project, out_path)

    logger.info("Using strategy {}".format(strategy.__class__))
    logger.info("update the node with basic information")
    # create constraints, clean name

    output = strategy.execute()

    # compress the output folder to a zip archieve and place it in the download directory
    # shutil.make_archive(os.path.join(download_dir), "zip", os.path.join(out_path))

    # if trad:
    # langs.to_po_file("./trad.po")
