import sys, getopt, os
from tricc.serializers.planuml import print_plantuml

from tricc.services.process_diagram import build_tricc_graph
import logging
import sys
sys.setrecursionlimit(100)

from tricc.strategies.xls_form import XLSFormStrategy
# set up logging to file
def setup_logger(logger_name, 
                 log_file, 
                 level=logging.INFO, 
                 format  ='[%(asctime)s] {%(pathname)s:%(lineno)d} %(levelname)s - %(message)s'):
     
    l = logging.getLogger(logger_name)
    formatter = logging.Formatter(format)
    fileHandler = logging.FileHandler(log_file, mode='w')
    fileHandler.setFormatter(formatter)
    streamHandler = logging.StreamHandler()
    streamHandler.setFormatter(formatter)

    l.setLevel(level)
    l.addHandler(fileHandler)
    l.addHandler(streamHandler)



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
        out_filepath= pre + 'xlsx'
    if out_filepath is None:
        # if output file path not specified, jsut take the name without extension
        formid= pre

    start_page = build_tricc_graph(in_filepath, out_filepath, formid)
    
    stategy = XLSFormStrategy()
    # create constaints, clean name
    stategy.process_base(start_page)
    # create relevance Expression
    stategy.process_relevance(start_page)
    # create calculate Expression
    stategy.process_calculate(start_page)
    
    stategy.process_export(start_page)


     