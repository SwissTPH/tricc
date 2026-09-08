"""Google Drive URL parsing and mocked downloads (no live Drive)."""

from __future__ import annotations

import os
from unittest.mock import patch

from tricc_oo.converters.google_drive import (
    extract_google_drive_file_id,
    extract_google_drive_folder_id,
    find_google_auth_json,
    is_google_drive_folder_url,
    is_google_drive_source,
    is_google_drive_url,
    resolve_google_drive_source,
)


def test_file_url_patterns():
    file_url = "https://drive.google.com/file/d/abc-FILE_id1/view?usp=drive_link"
    assert is_google_drive_url(file_url)
    assert not is_google_drive_folder_url(file_url)
    assert is_google_drive_source(file_url)
    assert extract_google_drive_file_id(file_url) == "abc-FILE_id1"
    uc = "https://drive.usercontent.google.com/download?id=xyz99"
    assert extract_google_drive_file_id(uc) == "xyz99"


def test_folder_url_patterns():
    folder = "https://drive.google.com/drive/folders/FOLDERID99"
    assert is_google_drive_folder_url(folder)
    assert extract_google_drive_folder_id(folder) == "FOLDERID99"
    nested = "https://drive.google.com/drive/u/0/folders/NESTEDID"
    assert extract_google_drive_folder_id(nested) == "NESTEDID"
    open_url = "https://drive.google.com/open?id=OPENID"
    assert is_google_drive_folder_url(open_url)
    assert extract_google_drive_folder_id(open_url) == "OPENID"


def test_find_auth_prefers_env(tmp_path, monkeypatch):
    env_file = tmp_path / "sa.json"
    env_file.write_text("{}", encoding="utf-8")
    monkeypatch.setenv("TRICC_GOOGLE_AUTH", str(env_file))
    found = find_google_auth_json(project_root=str(tmp_path / "missing"))
    assert found == str(env_file)


def test_find_auth_in_project_root(tmp_path, monkeypatch):
    monkeypatch.delenv("TRICC_GOOGLE_AUTH", raising=False)
    auth_dir = tmp_path / "auth"
    auth_dir.mkdir()
    creds = auth_dir / "google.json"
    creds.write_text("{}", encoding="utf-8")
    found = find_google_auth_json(project_root=str(tmp_path))
    assert found == str(creds)


def test_resolve_folder_filters_extensions(tmp_path):
    dest = tmp_path / "cache"
    dest.mkdir()
    keep = dest / "keep.drawio"
    keep.write_text("<mxfile/>", encoding="utf-8")
    entries = [
        {"id": "1", "name": "keep.drawio"},
        {"id": "2", "name": "notes.txt"},
        {"id": "3", "name": "skip.yaml"},
    ]
    with patch(
        "tricc_oo.converters.google_drive.list_google_drive_folder_files",
        return_value=entries,
    ), patch(
        "tricc_oo.converters.google_drive.download_google_drive_file",
        return_value=str(keep),
    ) as download:
        paths = resolve_google_drive_source(
            "https://drive.google.com/drive/folders/ABC",
            str(dest),
            valid_exts=(".drawio",),
        )
    download.assert_called_once()
    assert paths == [os.path.abspath(str(keep))]
