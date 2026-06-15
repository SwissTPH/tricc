# Strategy loading is now done via the registry (much cleaner + supports direct class usage)
from tricc_oo.strategies.registry import get_input_strategy, get_output_strategy
import getopt
import logging
import os
import sys
import gc
import re
import requests
import tempfile
from pathlib import Path
from urllib.parse import urlparse, parse_qs

# Google API imports for authenticated Drive access
# pip install google google-api-python-client
try:
    from google.oauth2 import service_account
    from googleapiclient.discovery import build
    from googleapiclient.http import MediaIoBaseDownload
    GOOGLE_AUTH_AVAILABLE = True
except ImportError:
    GOOGLE_AUTH_AVAILABLE = False
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
    print("-i / --input draw.io filepath (MANDATORY) or directory containing drawio files, or Google Drive URL")
    print("-o / --output xls file ")
    print("-d form_id ")
    print("-s L4 system/strategy (odk, cht, cc)")
    print("-h / --help print that menu")


def is_google_drive_url(url):
    """Check if the given string is a Google Drive URL."""
    return url.startswith("https://drive.usercontent.google.com/download?id=") or url.startswith("https://drive.google.com/file/d/")


def extract_google_drive_file_id(url):
    """Extract file ID from Google Drive URL."""
    # Pattern: https://drive.google.com/file/d/{file_id}/view?usp=drive_link
    match = re.search(r'https://drive.usercontent.google.com/download\?id=([a-zA-Z0-9_-]+)', url)
    if match:
        return match.group(1)
    else:
        match = re.search(r'https://drive.google.com/file/d/([a-zA-Z0-9_-]+)', url)
        if match:
            return match.group(1)
    return None


def download_google_drive_file(file_id, temp_dir, original_url=None):
    """Download a file from Google Drive using authenticated access and return the local path.

    Uses system temp directory and tries authenticated access first, falls back to direct download.
    """
    # Use system temp directory
    if not temp_dir:
        temp_dir = tempfile.gettempdir()

    # Try authenticated download first
    if GOOGLE_AUTH_AVAILABLE:
        auth_path = os.path.join(os.path.dirname(__file__), '..', '.secrets', 'google.json')
        auth_path = os.path.abspath(auth_path)

        if os.path.exists(auth_path):
            try:
                logger.info(f"Attempting authenticated download using service account: {auth_path}")
                credentials = service_account.Credentials.from_service_account_file(
                    auth_path, scopes=['https://www.googleapis.com/auth/drive.readonly']
                )

                service = build('drive', 'v3', credentials=credentials)

                # Get file metadata to determine filename
                file_metadata = service.files().get(fileId=file_id, fields='name,mimeType').execute()
                filename = file_metadata.get('name', f"{file_id}")

                # Create temp file path
                local_path = os.path.join(temp_dir, f"drive_{file_id}_{filename}")

                # Download the file
                request = service.files().get_media(fileId=file_id)
                with open(local_path, 'wb') as f:
                    downloader = MediaIoBaseDownload(f, request)
                    done = False
                    while done is False:
                        status, done = downloader.next_chunk()
                        logger.debug(f"Download {int(status.progress() * 100)}%.")

                logger.info(f"Successfully downloaded Google Drive file to temp location: {local_path}")
                return local_path

            except Exception as auth_error:
                logger.warning(f"Authenticated download failed: {auth_error}. Falling back to direct download.")

    # Fallback to direct download (for public files)
    try:
        logger.info("Attempting direct download (fallback for public files)")
        download_url = f"https://drive.google.com/uc?export=download&id={file_id}"
        response = requests.get(download_url, stream=True, timeout=30)

        if response.status_code == 200:
            # Try to get filename from Content-Disposition header
            content_disposition = response.headers.get('Content-Disposition', '')
            filename_match = re.search(r'filename=["\']?([^"\']+)["\']?', content_disposition)

            if filename_match:
                filename = filename_match.group(1)
            else:
                # Fallback: use file ID as filename with .drawio extension
                filename = f"{file_id}.drawio"

            local_path = os.path.join(temp_dir, f"drive_{file_id}_{filename}")

            # Download the file
            with open(local_path, 'wb') as f:
                for chunk in response.iter_content(chunk_size=8192):
                    if chunk:
                        f.write(chunk)

            logger.info(f"Downloaded Google Drive file via direct link to temp location: {local_path}")
            return local_path

        elif "confirm=" in response.url:
            # Google requires confirmation for large files
            logger.error("Google Drive file requires confirmation token. Large files need authenticated access.")
            return None
        else:
            logger.error(f"Failed to download Google Drive file. Status code: {response.status_code}")
            return None

    except Exception as e:
        logger.error(f"Error downloading Google Drive file: {e}")
        return None


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
        opts, args = getopt.getopt(sys.argv[1:], "hti:o:s:I:O:l:d:D:", ["input=", "output=", "help", "trads"])
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
        setup_logger("default", debug_file_path, logging.INFO)
    else:
        setup_logger("default", debug_file_path, logging.INFO)
    file_content = []
    files = []
    downloaded_files = []  # Track downloaded files for cleanup

    # Handle comma-separated inputs (files, directories, or Google Drive URLs)
    in_filepath_list = in_filepath.split(",")
    for current_input in in_filepath_list:
        current_input = current_input.strip()

        if is_google_drive_url(current_input):
            # Handle Google Drive URL
            logger.info(f"Detected Google Drive URL: {current_input}")
            file_id = extract_google_drive_file_id(current_input)
            if file_id:
                logger.info(f"Extracted file ID: {file_id}")
                # Use temp directory for Google Drive downloads
                temp_dir = tempfile.gettempdir()
                local_path = download_google_drive_file(file_id, temp_dir, current_input)
                if local_path:
                    downloaded_files.append(local_path)
                    files.append(local_path)
                    logger.info(f"Successfully processed Google Drive file: {local_path}")
                else:
                    logger.error(f"Failed to download Google Drive file: {current_input}")
                    sys.exit(1)  # Exit on download failure as requested
            else:
                logger.error(f"Could not extract file ID from Google Drive URL: {current_input}")
                sys.exit(1)
        else:
            # Handle local files/directories
            # Accept common formats used by input strategies (.drawio, .yaml/.yml for testing, etc.)
            valid_exts = (".drawio", ".yaml", ".yml")
            if os.path.isdir(current_input):
                for f in os.listdir(current_input):
                    if f.lower().endswith(valid_exts):
                        files.append(os.path.join(current_input, f))
            elif os.path.isfile(current_input) and current_input.lower().endswith(valid_exts):
                files.append(current_input)
            else:
                logger.warning(f"Skipping invalid input (unknown extension): {current_input}")

    # Read content from all files
    for f in files:
        try:
            with open(f, "r", encoding='utf-8') as s:
                content = s.read()
                file_content.append(content)
                logger.info(f"Loaded file: {f}")
        except Exception as e:
            logger.error(f"Error reading file {f}: {e}")

    if not file_content:
        logger.critical("No valid drawio files found or loaded")
        exit(1)

    InputStrategyCls = get_input_strategy(input_strategy)
    strategy = InputStrategyCls(files)
    logger.info(f"build the graph from strategy {InputStrategyCls.__name__}")
    media_path = os.path.join(out_path, "media-tmp")
    project = strategy.execute(file_content, media_path)

    OutputStrategyCls = get_output_strategy(output_strategy)
    strategy = OutputStrategyCls(project, out_path)

    logger.info("Using strategy {}".format(OutputStrategyCls.__name__))
    logger.info("update the node with basic information")
    # create constraints, clean name

    output = strategy.execute()

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
