"""Tests for draw.io image extract + optional max-dimension resize."""

from __future__ import annotations

import base64
import io
import os

from PIL import Image

from tricc_oo.converters.image_media import (
    effective_caps,
    maybe_resize_image,
    parse_embedded_image,
    write_image_file,
)
from tricc_oo.converters.xml_to_tricc import add_image_from_style


def _png_bytes(width: int, height: int) -> bytes:
    img = Image.new("RGB", (width, height), color=(20, 40, 80))
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


def _jpeg_bytes(width: int, height: int) -> bytes:
    img = Image.new("RGB", (width, height), color=(200, 10, 10))
    buf = io.BytesIO()
    img.save(buf, format="JPEG", quality=95)
    return buf.getvalue()


def test_effective_caps_inherit_and_zero():
    assert effective_caps(1200, 1200, 400, None) == (400, 1200)
    assert effective_caps(1200, 1200, None, 0) == (1200, None)
    assert effective_caps(None, None, None, None) == (None, None)


def test_parse_embedded_image_style():
    payload = base64.b64encode(b"abc").decode("ascii")
    style = f"shape=image;image=data:image/png,{payload};"
    assert parse_embedded_image(style) == ("png", payload)


def test_png_over_cap_is_resized(tmp_path):
    raw = _png_bytes(200, 150)
    out = maybe_resize_image(raw, "png", 100, None)
    img = Image.open(io.BytesIO(out))
    assert img.size == (100, 75)
    assert img.format == "PNG"


def test_png_already_fits_is_byte_identical():
    raw = _png_bytes(80, 60)
    assert maybe_resize_image(raw, "png", 100, 100) == raw


def test_svg_never_resized():
    raw = b"<svg xmlns='http://www.w3.org/2000/svg'></svg>"
    assert maybe_resize_image(raw, "svg+xml", 10, 10) == raw


def test_jpeg_keeps_jpeg(tmp_path):
    raw = _jpeg_bytes(200, 100)
    out = maybe_resize_image(raw, "jpeg", 100, 100)
    img = Image.open(io.BytesIO(out))
    assert img.size[0] <= 100
    assert img.size[1] <= 100
    assert img.format == "JPEG"


def test_add_image_from_style_writes_resized(tmp_path):
    raw = _png_bytes(200, 150)
    payload = base64.b64encode(raw).decode("ascii")
    style = f"shape=image;image=data:image/png,{payload};"

    class Caps:
        image_max_width = 100
        image_max_height = None

    name, stored = add_image_from_style(style, str(tmp_path), project=Caps())
    assert name.endswith(".png")
    on_disk = os.path.join(tmp_path, "images", name)
    assert os.path.isfile(on_disk)
    img = Image.open(on_disk)
    assert img.size == (100, 75)
    with open(on_disk, "rb") as handle:
        assert base64.b64decode(stored) == handle.read()


def test_write_image_file_hashes_output_bytes(tmp_path):
    data = b"hello-image"
    name, payload = write_image_file(str(tmp_path), "png", data)
    assert name.endswith(".png")
    assert base64.b64decode(payload) == data
