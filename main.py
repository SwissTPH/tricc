import getopt
import gettext
import logging
import os
import sys

# set up logging to file
from babel import Locale

from tricc.services.process_diagram import build_tricc_graph
from tricc.strategies.xls_form import XLSFormStrategy

#gettext.bindtextdomain('tricc', './locale/')
#gettext.textdomain('tricc')
language =   Locale('Fr')
fr =  gettext.translation('tricc', './locales' , languages=['fr'])
fr.install()


def setup_logger(logger_name,
                 log_file, 
                 level=logging.INFO, 
                 formatting  ='[%(asctime)s] {%(pathname)s:%(lineno)d} %(levelname)s - %(message)s'):
     
    l = logging.getLogger(logger_name)
    formatter = logging.Formatter(formatting)
    file_handler = logging.FileHandler(log_file, mode='w')
    file_handler.setFormatter(formatter)
    stream_handler = logging.StreamHandler()
    stream_handler.setFormatter(formatter)

    l.setLevel(level)
    l.addHandler(file_handler)

setup_logger('default', "debug.log", logging.DEBUG)

logger = logging.getLogger('default')

# set up logging to console
console = logging.StreamHandler()
console.setLevel(logging.INFO)
# set a format which is simpler for console use
formatter = logging.Formatter('%(name)-12s: %(levelname)-8s %(message)s')
console.setFormatter(formatter)
# add the handler to the root logger
logging.getLogger('').addHandler(console)

def print_help():
    print('-i / --input draw.io filepath (MANDATORY)')
    print('-o / --output xls file ')
    print('-d formid ')
    print('-s L4 system/strategy (odk, cht, cc)')
    print('-h / --help print that menu')

    
if __name__ == "__main__":
    system='odk'
    in_filepath= None
    out_filepath=None
    formid=None
    try:
      opts, args = getopt.getopt(sys.argv[1:],"hi:o:s:",["input=","output=","help"])
    except getopt.GetoptError:
        print_help()
        sys.exit(2)
    for opt, arg in opts:
        if opt in ('-h', '--help'):
            print_help()
            sys.exit()
        elif opt in ("-i", "--input"):
            in_filepath = arg
        elif opt == "-o":
            out_filepath = arg
        elif opt == "-s":
            strategy = arg
        elif opt == "-d":
            formid = arg
    if in_filepath is None:
        print_help()
        sys.exit(2)
    pre, ext = os.path.splitext(in_filepath)
    if out_filepath is None:
        # if output file path not specified, just chagne the extension
        out_filepath= pre + '.xlsx'
    if out_filepath is None:
        # if output file path not specified, just take the name without extension
        formid= pre
    logger.info("build the graph from XML")
    start_page = build_tricc_graph(in_filepath)
    
    strategy = XLSFormStrategy()
    logger.info("Using strategy {}".format(strategy.__class__))
    logger.info("update the node with basic information")
    # create constraints, clean name
    strategy.process_base(start_page)
    logger.info("generate the relevance based on edges")
    # create relevance Expression
    strategy.process_relevance(start_page)
    logger.info("generate the calculate based on edges")
    
    # create calculate Expression
    strategy.process_calculate(start_page)
    logger.info("generate the export format")
    
    strategy.process_export(start_page)
    logger.info("print the export")
    if start_page.root.form_id is not None:
        formid= start_page.root.form_id 
    strategy.do_export(start_page.root.label,out_filepath, formid)


     