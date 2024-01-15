import getopt
import gettext
import logging
import os
import sys
import gc
import tomllib
from pathlib import Path
import yaml

# set up logging to file
from tricc.models.lang import SingletonLangClass

# gettext.bindtextdomain('tricc', './locale/')
# gettext.textdomain('tricc')
import sys
import codecs

langs = SingletonLangClass()

# fr =  gettext.translation('tricc', './locales' , languages=['fr'])
# fr.install()
# en =  gettext.translation('tricc', './locales' , languages=['en'])
# en.install()


# langs.add_trad('fr', fr)
# langs.add_trad('en', en)

from tricc.strategies.input.drawio import DrawioStrategy
from tricc.strategies.input.medalcreator import MedalCStrategy

# from tricc.serializers.medalcreator import execute

from tricc.strategies.output.xls_form import XLSFormStrategy
from tricc.strategies.output.xlsform_cdss import XLSFormCDSSStrategy
from tricc.strategies.output.xlsform_cht import XLSFormCHTStrategy


def setup_logger(
    logger_name,
    log_file,
    level=logging.INFO,
    formatting="[%(asctime)s] {%(pathname)s:%(lineno)d} %(levelname)s - %(message)s",
):
    l = logging.getLogger(logger_name)
    formatter = logging.Formatter(formatting)
    file_handler = logging.FileHandler(log_file, mode="w", encoding="utf-8")  # Set the encoding to utf-8
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
    # gc.disable()

    config = sys.argv

    if config[1] is None:
        logger.error("no config file provided, aborting")
        exit()
    elif config[1] == "-h" or config[1] == "--help":
        print_help()
        exit()
    else:
        base_path = Path(__file__).parent.resolve()
        with open(Path(base_path, "baseconfig.toml"), "rb") as c:
            base_config = tomllib.load(c)
            upload_path = base_config["upload_folder"]

        toml_config_path = Path(upload_path + config[1] + ".toml")
        if Path.is_file(toml_config_path):
            with open(toml_config_path, "rb") as f:
                params = tomllib.load(f)
        else:
            yaml_config_path = Path(upload_path + config[1] + ".yaml")
            with open(yaml_config_path, "rb") as f:
                params = yaml.load(f, Loader=yaml.SafeLoader)

    system = params["system"]
    # in_filepath= None
    in_filepath = params["in_filepath"]
    # out_path=None
    out_path = params["out_path"]
    # form_id=None
    form_id = params["form_id"]
    # debug_level=None
    debug_level = params["debug_level"]
    # trad = False
    trad = params["trad"]
    # input_strategy = 'DrawioStrategy'
    input_strategy = params["input_strategy"]
    # output_strategy= 'XLSFormStrategy'
    output_strategy = params["output_strategy"]
    # conversion_ID
    conversion_id = str(params["conversion_ID"])
    # download_dir
    download_dir = params["download_dir"]

    if in_filepath is None:
        print_help()
        exit()

    # try:
    #   opts, args = getopt.getopt(sys.argv[1:],"hti:o:s:I:O:l:",["input=","output=","help","trads"])
    # except getopt.GetoptError:
    #     print_help()
    #     sys.exit(2)
    # for opt, arg in opts:
    #     if opt in ('-h', '--help'):
    #         print_help()
    #         sys.exit()
    #     elif opt in ("-i", "--input"):
    #         in_filepath = arg
    #     elif opt == "-o":
    #         out_path = arg
    #     elif opt == "-I":
    #         input_strategy = arg
    #     elif opt == "-O":
    #         output_strategy = arg
    #     elif opt == "-d":
    #         form_id = arg
    #     elif opt == "-l":
    #         debug_level = arg
    #     elif opt in ("-t", "--trads"):
    #         trad = True
    # if in_filepath is None:
    #     print_help()
    #     sys.exit(2)

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
    media_path = os.path.join(out_path, conversion_id, "media-tmp")
    start_page, pages = strategy.execute(in_filepath, media_path)

    strategy = globals()[output_strategy](out_path)

    logger.info("Using strategy {}".format(strategy.__class__))
    logger.info("update the node with basic information")
    # create constraints, clean name

    strategy.execute(
        start_page, pages=pages, conversion_id=conversion_id, download_dir=download_dir
    )

    if trad:
        langs.to_po_file("./trad.po")

    # print the debug file to the console
    debug_file_path = os.path.join(os.path.dirname(__file__), "debug.log")
    with open(debug_file_path, "r") as f:
        debug_file_contents = f.read()
    print(debug_file_contents)
