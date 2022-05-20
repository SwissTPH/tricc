import sys, getopt, os

from tricc.services.process_diagram import process_diagram
import logging
# set up logging to file
logging.basicConfig(
     filename='log_file_name.log',
     level=logging.INFO, 
     format= '[%(asctime)s] {%(pathname)s:%(lineno)d} %(levelname)s - %(message)s',
     datefmt='%H:%M:%S'
 )

# set up logging to console
console = logging.StreamHandler()
console.setLevel(logging.DEBUG)
# set a format which is simpler for console use
formatter = logging.Formatter('%(name)-12s: %(levelname)-8s %(message)s')
console.setFormatter(formatter)
# add the handler to the root logger
logging.getLogger('').addHandler(console)

def print_help():
    print('-i / --input draw.io filepath (MANDATORY)')
    print('-o / --output xls file ')
    print('-d formid ')
    print('-s L4 system (odk, cht, cc)')
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
            system = arg
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
        
    process_diagram(in_filepath, out_filepath, formid)
