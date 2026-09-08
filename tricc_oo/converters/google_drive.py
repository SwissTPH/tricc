"""Download Google Drive files/folders for TRICC inputs (CLI ``-i`` and ``tricc.yaml`` segment)."""

from __future__ import annotations

import logging
import os
import re
import tempfile
from typing import Iterable, List, Optional
from urllib.parse import parse_qs, urlparse

import requests

logger = logging.getLogger("default")

try:
    from google.oauth2 import service_account
    from googleapiclient.discovery import build
    from googleapiclient.http import MediaIoBaseDownload

    GOOGLE_AUTH_AVAILABLE = True
except ImportError:
    GOOGLE_AUTH_AVAILABLE = False
    service_account = None  # type: ignore
    build = None  # type: ignore
    MediaIoBaseDownload = None  # type: ignore

DRIVE_READONLY_SCOPE = "https://www.googleapis.com/auth/drive.readonly"


def is_google_drive_url(url: str) -> bool:
    if not url:
        return False
    return url.startswith("https://drive.usercontent.google.com/download?id=") or url.startswith(
        "https://drive.google.com/file/d/"
    )


def is_google_drive_folder_url(url: str) -> bool:
    if not url:
        return False
    return (
        "https://drive.google.com/drive/folders/" in url
        or ("https://drive.google.com/drive/u/" in url and "/folders/" in url)
        or "https://drive.google.com/open?id=" in url
    )


def is_google_drive_source(url: str) -> bool:
    return is_google_drive_url(url) or is_google_drive_folder_url(url)


def extract_google_drive_file_id(url: str) -> Optional[str]:
    match = re.search(r"https://drive.usercontent.google.com/download\?id=([a-zA-Z0-9_-]+)", url)
    if match:
        return match.group(1)
    match = re.search(r"https://drive.google.com/file/d/([a-zA-Z0-9_-]+)", url)
    if match:
        return match.group(1)
    return None


def extract_google_drive_folder_id(url: str) -> Optional[str]:
    match = re.search(r"https://drive.google.com/drive/folders/([a-zA-Z0-9_-]+)", url)
    if match:
        return match.group(1)
    match = re.search(r"https://drive.google.com/drive/u/\d+/folders/([a-zA-Z0-9_-]+)", url)
    if match:
        return match.group(1)
    parsed_url = urlparse(url)
    if parsed_url.netloc == "drive.google.com":
        folder_ids = parse_qs(parsed_url.query).get("id", [])
        if folder_ids:
            return folder_ids[0]
    return None


def find_google_auth_json(project_root: Optional[str] = None) -> Optional[str]:
    """Locate service-account credentials (env, project, cwd, TRICC checkout)."""
    candidates = []
    env_path = os.environ.get("TRICC_GOOGLE_AUTH")
    if env_path:
        candidates.append(env_path)
    if project_root:
        candidates.append(os.path.join(project_root, "auth", "google.json"))
    candidates.append(os.path.join(os.getcwd(), "auth", "google.json"))
    pkg_root = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
    candidates.append(os.path.join(pkg_root, "auth", "google.json"))
    for path in candidates:
        if path and os.path.isfile(path):
            return os.path.abspath(path)
    return None


def get_drive_service(project_root: Optional[str] = None):
    """Return an authenticated Google Drive client, or None."""
    if not GOOGLE_AUTH_AVAILABLE:
        return None
    auth_path = find_google_auth_json(project_root)
    if not auth_path:
        return None
    credentials = service_account.Credentials.from_service_account_file(
        auth_path,
        scopes=[DRIVE_READONLY_SCOPE],
    )
    return build("drive", "v3", credentials=credentials)


def list_google_drive_folder_files(folder_id: str, drawio_only: bool = True, project_root: Optional[str] = None):
    """List files in a Google Drive folder (not nested subfolders)."""
    try:
        service = get_drive_service(project_root)
        if service is None:
            logger.error(
                "Google Drive folder listing requires service account auth "
                "(missing Google libs, TRICC_GOOGLE_AUTH, or auth/google.json)."
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
                            "Could not resolve shortcut target for %s: %s",
                            file_item.get("name", "unknown"),
                            exc,
                        )
                continue
            expanded_files.append(file_item)

        if not drawio_only:
            return expanded_files
        return [f for f in expanded_files if (f.get("name") or "").lower().endswith(".drawio")]
    except Exception as exc:
        logger.error("Error listing Google Drive folder files: %s", exc)
        return []


def download_google_drive_file(
    file_id: str,
    temp_dir: Optional[str] = None,
    original_url: Optional[str] = None,
    project_root: Optional[str] = None,
) -> Optional[str]:
    """Download one Drive file to ``temp_dir``. Auth first, then public direct link."""
    if not temp_dir:
        temp_dir = tempfile.gettempdir()
    os.makedirs(temp_dir, exist_ok=True)

    if GOOGLE_AUTH_AVAILABLE:
        try:
            service = get_drive_service(project_root)
            if service is None:
                raise RuntimeError("No service account auth available")
            logger.info("Attempting authenticated download using service account")
            file_metadata = service.files().get(
                fileId=file_id,
                fields="name,mimeType",
                supportsAllDrives=True,
            ).execute()
            filename = os.path.basename(file_metadata.get("name", f"{file_id}"))
            filename = filename.replace("/", "_").replace("\\", "_")
            local_path = os.path.join(temp_dir, f"drive_{file_id}_{filename}")
            request = service.files().get_media(fileId=file_id, supportsAllDrives=True)
            with open(local_path, "wb") as handle:
                downloader = MediaIoBaseDownload(handle, request)
                done = False
                while not done:
                    status, done = downloader.next_chunk()
                    if status:
                        logger.debug("Download %s%%.", int(status.progress() * 100))
            logger.info("Downloaded Google Drive file to %s", local_path)
            return local_path
        except Exception as auth_error:
            logger.warning("Authenticated download failed: %s. Falling back to direct download.", auth_error)

    try:
        logger.info("Attempting direct download (fallback for public files)")
        download_url = f"https://drive.google.com/uc?export=download&id={file_id}"
        response = requests.get(download_url, stream=True, timeout=30)
        if response.status_code == 200:
            content_disposition = response.headers.get("Content-Disposition", "")
            filename_match = re.search(r'filename=["\']?([^"\']+)["\']?', content_disposition)
            filename = os.path.basename(filename_match.group(1) if filename_match else f"{file_id}.drawio")
            filename = filename.replace("/", "_").replace("\\", "_")
            local_path = os.path.join(temp_dir, f"drive_{file_id}_{filename}")
            with open(local_path, "wb") as handle:
                for chunk in response.iter_content(chunk_size=8192):
                    if chunk:
                        handle.write(chunk)
            logger.info("Downloaded Google Drive file via direct link to %s", local_path)
            return local_path
        if "confirm=" in (response.url or ""):
            logger.error("Google Drive file requires confirmation token. Large files need authenticated access.")
            return None
        logger.error("Failed to download Google Drive file. Status code: %s", response.status_code)
        return None
    except Exception as exc:
        logger.error("Error downloading Google Drive file: %s", exc)
        return None


def resolve_google_drive_source(
    url: str,
    dest_dir: str,
    valid_exts: Iterable[str] = (".drawio",),
    project_root: Optional[str] = None,
) -> List[str]:
    """Download a Drive file or the files in a Drive folder. Returns local paths."""
    exts = tuple(e.lower() for e in valid_exts)
    os.makedirs(dest_dir, exist_ok=True)
    paths: List[str] = []
    if is_google_drive_folder_url(url):
        folder_id = extract_google_drive_folder_id(url)
        if not folder_id:
            raise ValueError(f"Could not extract folder ID from Google Drive URL: {url}")
        entries = list_google_drive_folder_files(folder_id, drawio_only=False, project_root=project_root)
        for entry in entries:
            name = (entry.get("name") or "").lower()
            if not name.endswith(exts):
                continue
            file_id = entry.get("id")
            if not file_id:
                continue
            local_path = download_google_drive_file(file_id, dest_dir, url, project_root=project_root)
            if local_path:
                paths.append(os.path.abspath(local_path))
            else:
                logger.warning("Failed to download Drive file %s (%s)", entry.get("name"), file_id)
        return sorted(paths)
    if is_google_drive_url(url):
        file_id = extract_google_drive_file_id(url)
        if not file_id:
            raise ValueError(f"Could not extract file ID from Google Drive URL: {url}")
        local_path = download_google_drive_file(file_id, dest_dir, url, project_root=project_root)
        if not local_path:
            return []
        if not local_path.lower().endswith(exts):
            logger.warning("Downloaded Drive file does not match expected extensions %s: %s", exts, local_path)
            return []
        return [os.path.abspath(local_path)]
    raise ValueError(f"Not a Google Drive URL: {url}")
