import getopt
import gettext
import logging
import os
import sys
import gc

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
from tricc_oo.strategies.input.medalcreator import MedalCStrategy

# from tricc_oo.serializers.medalcreator import execute

from tricc_oo.strategies.output.xls_form import XLSFormStrategy
from tricc_oo.strategies.output.xlsform_cdss import XLSFormCDSSStrategy
from tricc_oo.strategies.output.xlsform_cht import XLSFormCHTStrategy


def setup_logger(
    logger_name,
    log_file,
    level=logging.INFO,
    formatting="[%(asctime)s] {%(pathname)s:%(lineno)d} %(levelname)s - %(message)s",
):
    l = logging.getLogger(logger_name)
    formatter = logging.Formatter(formatting)
    file_handler = logging.FileHandler(log_file, mode="w")
    file_handler.setFormatter(formatter)
    stream_handler = logging.StreamHandler()
    stream_handler.setFormatter(formatter)

    l.setLevel(level)
    l.addHandler(file_handler)


logger = logging.getLogger("default")

# set up logging to console
console = logging.StreamHandler()
console.setLevel(logging.INFO)
# set a format which is simpler for console use
formatter = logging.Formatter("%(name)-12s: %(levelname)-8s %(message)s")
console.setFormatter(formatter)
# add the handler to the root logger
logging.getLogger("").addHandler(console)

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

    input_strategy = "DrawioStrategy"
    output_strategy = "XLSFormStrategy"
    try:
        opts, args = getopt.getopt(
            sys.argv[1:], "hti:o:s:I:O:l:d:", ["input=", "output=", "help", "trads"]
        )
    except getopt.GetoptError:
        print_help()
        sys.exit(2)
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
    if in_filepath is None:
        print_help()
        sys.exit(2)

    if debug_level is not None:
        setup_logger("default", "debug.log", LEVELS[debug_level])
    elif "pydevd" in sys.modules:
        setup_logger("default", "debug.log", logging.DEBUG)
    else:
        setup_logger("default", "debug.log", logging.INFO)

    pre, ext = os.path.splitext(in_filepath)
    if out_path is None:
        # if output file path not specified, just chagne the extension
        out_path = os.path.dirname(pre)
    strategy = globals()[input_strategy](in_filepath)
    logger.info(f"build the graph from strategy {input_strategy}")
    media_path = os.path.join(out_path, "media-tmp")
    start_page, pages = strategy.execute(in_filepath, media_path)

    strategy = globals()[output_strategy](out_path)

    logger.info("Using strategy {}".format(strategy.__class__))
    logger.info("update the node with basic information")
    # create constraints, clean name

    strategy.execute(start_page, pages=pages)

    if trad:
        langs.to_po_file("./trad.po")
