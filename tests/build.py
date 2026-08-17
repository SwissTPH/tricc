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
    print("-i / --input file path, folder path, or Google Drive file/folder URL (MANDATORY; comma-separated allowed)")
    print("-o / --output xls file ")
    print("-d form_id ")
    print("-s L4 system/strategy (odk, cht, cc)")
    print("-h / --help print that menu")


def is_google_drive_url(url):
    """Check if the given string is a Google Drive URL."""
    return url.startswith("https://drive.usercontent.google.com/download?id=") or url.startswith("https://drive.google.com/file/d/")


def is_google_drive_folder_url(url):
    """Check if the given string is a Google Drive folder URL."""
    return (
        "https://drive.google.com/drive/folders/" in url
        or "https://drive.google.com/drive/u/" in url and "/folders/" in url
        or "https://drive.google.com/open?id=" in url
    )


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


def extract_google_drive_folder_id(url):
    """Extract folder ID from Google Drive folder URL."""
    match = re.search(r'https://drive.google.com/drive/folders/([a-zA-Z0-9_-]+)', url)
    if match:
        return match.group(1)

    match = re.search(r'https://drive.google.com/drive/u/\d+/folders/([a-zA-Z0-9_-]+)', url)
    if match:
        return match.group(1)

    parsed_url = urlparse(url)
    if parsed_url.netloc == "drive.google.com":
        query_params = parse_qs(parsed_url.query)
        folder_ids = query_params.get("id", [])
        if folder_ids:
            return folder_ids[0]

    return None


def get_drive_service():
    """Return an authenticated Google Drive service client when available."""
    if not GOOGLE_AUTH_AVAILABLE:
        return None

    auth_path = os.path.join(os.path.dirname(__file__), '..', 'auth', 'google.json')
    auth_path = os.path.abspath(auth_path)
    if not os.path.exists(auth_path):
        return None

    credentials = service_account.Credentials.from_service_account_file(
        auth_path,
        scopes=['https://www.googleapis.com/auth/drive.readonly']
    )
    return build('drive', 'v3', credentials=credentials)


def list_google_drive_folder_files(folder_id, drawio_only=True):
    """List files in a Google Drive folder."""
    try:
        service = get_drive_service()
        if service is None:
            logger.error(
                "Google Drive folder listing requires service account auth "
                "(missing Google libs or auth/google.json)."
            )
            return []

        files = []
        page_token = None
        while True:
            response = service.files().list(
                q=f"'{folder_id}' in parents and trashed=false",
                fields=(
                    "nextPageToken, "
                    "files(id, name, mimeType, shortcutDetails/targetId, shortcutDetails/targetMimeType)"
                ),
                pageSize=1000,
                pageToken=page_token,
                includeItemsFromAllDrives=True,
                supportsAllDrives=True,
            ).execute()
            files.extend(response.get("files", []))
            page_token = response.get("nextPageToken", None)
            if page_token is None:
                break

        expanded_files = []
        for file_item in files:
            mime_type = file_item.get("mimeType")
            if mime_type == "application/vnd.google-apps.folder":
                continue

            if mime_type == "application/vnd.google-apps.shortcut":
                target_id = file_item.get("shortcutDetails", {}).get("targetId")
                if target_id:
                    try:
                        target_meta = service.files().get(
                            fileId=target_id,
                            fields="id,name,mimeType",
                            supportsAllDrives=True,
                        ).execute()
                        expanded_files.append(target_meta)
                    except Exception as exc:
                        logger.warning(
                            f"Could not resolve shortcut target for {file_item.get('name', 'unknown')}: {exc}"
                        )
                continue

            expanded_files.append(file_item)

        non_folders = expanded_files
        if not drawio_only:
            return non_folders
        return [f for f in non_folders if f.get("name", "").lower().endswith(".drawio")]
    except Exception as exc:
        logger.error(f"Error listing Google Drive folder files: {exc}")
        return []


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


def download_google_drive_file(file_id, temp_dir, original_url=None):
    """Download a file from Google Drive using authenticated access and return the local path.

    Uses system temp directory and tries authenticated access first, falls back to direct download.
    """
    # Use system temp directory
    if not temp_dir:
        temp_dir = tempfile.gettempdir()

    # Try authenticated download first
    if GOOGLE_AUTH_AVAILABLE:
        try:
            try:
                service = get_drive_service()
                if service is None:
                    raise RuntimeError("No service account auth available")
                logger.info("Attempting authenticated download using service account")

                # Get file metadata to determine filename
                file_metadata = service.files().get(
                    fileId=file_id,
                    fields='name,mimeType',
                    supportsAllDrives=True
                ).execute()
                filename = file_metadata.get('name', f"{file_id}")

                # Create temp file path
                local_path = os.path.join(temp_dir, f"drive_{file_id}_{filename}")

                # Download the file
                request = service.files().get_media(fileId=file_id, supportsAllDrives=True)
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
        except Exception:
            pass

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
    #output_strategy = "XLSFormCHTStrategy"
    output_strategy = "XLSFormCDSSStrategy"
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
    #TODO: add project config to consider the options threshold for the multiple choice questions 
    project_config={
        "title": "My project",
        "description": "",
        "lang_code": "en",
        "options_threshold": 30,
    }
    files = []
    downloaded_files = []  # Track downloaded files for cleanup

    # Handle comma-separated inputs (files, directories, or Google Drive URLs)
    in_filepath_list = in_filepath.split(",")
    for current_input in in_filepath_list:
        current_input = current_input.strip()

        if is_google_drive_folder_url(current_input):
            logger.info(f"Detected Google Drive folder URL: {current_input}")
            folder_id = extract_google_drive_folder_id(current_input)
            if not folder_id:
                logger.error(f"Could not extract folder ID from Google Drive URL: {current_input}")
                sys.exit(1)

            folder_files = list_google_drive_folder_files(folder_id, drawio_only=True)
            if not folder_files:
                logger.error(f"No .drawio files found (or folder inaccessible): {current_input}")
                sys.exit(1)
            logger.info(f"Found {len(folder_files)} .drawio file(s) in folder.")

            for drive_file in folder_files:
                file_id = drive_file.get("id")
                file_name = drive_file.get("name", file_id)
                if not file_id:
                    continue
                local_path = download_google_drive_file(file_id, tempfile.gettempdir(), current_input)
                if local_path:
                    downloaded_files.append(local_path)
                    files.append(local_path)
                    logger.info(f"Downloaded from folder: {file_name}")
                else:
                    logger.warning(f"Failed to download file from folder: {file_name} ({file_id})")

        elif is_google_drive_url(current_input):
            # Handle Google Drive file URL (single file only; use a folder URL for multiple files)
            logger.info(f"Detected Google Drive file URL: {current_input}")
            file_id = extract_google_drive_file_id(current_input)
            if file_id:
                logger.info(f"Extracted file ID: {file_id}")
                temp_dir = tempfile.gettempdir()
                local_path = download_google_drive_file(file_id, temp_dir, current_input)
                if local_path:
                    downloaded_files.append(local_path)
                    add_unique_files(files, [local_path])
                    logger.info(f"Successfully processed Google Drive file: {local_path}")
                else:
                    logger.error(f"Failed to download Google Drive file: {current_input}")
                    sys.exit(1)
            else:
                logger.error(f"Could not extract file ID from Google Drive URL: {current_input}")
                sys.exit(1)
        else:
            # Handle local files/directories
            # Accept common formats used by input strategies (.drawio, .yaml/.yml for testing, etc.)
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
