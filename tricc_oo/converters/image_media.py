"""Decode draw.io-embedded images and optionally fit them to a pixel box."""

from __future__ import annotations

import base64
import hashlib
import io
import logging
import os
from typing import Any, Mapping, Optional, Tuple

logger = logging.getLogger("default")

try:
    from PIL import Image, ImageOps
except ImportError:  # pragma: no cover
    Image = None  # type: ignore
    ImageOps = None  # type: ignore

try:
    RESAMPLE = Image.Resampling.LANCZOS  # type: ignore[union-attr]
except AttributeError:  # pragma: no cover - older Pillow
    RESAMPLE = getattr(Image, "LANCZOS", None)

VECTOR_TYPES = {"svg", "svg+xml"}
LOSSLESS_TYPES = {"png", "gif", "webp", "bmp", "tiff", "tif"}
JPEG_TYPES = {"jpeg", "jpg"}


def parse_max_attr(value: Any) -> Optional[int]:
    """Parse a draw.io ``max_width`` / ``max_height`` attribute. ``0`` = unlimited."""
    if value is None or value == "":
        return None
    try:
        number = int(value)
    except (TypeError, ValueError):
        logger.warning("Ignoring non-integer image cap %r", value)
        return None
    if number < 0:
        logger.warning("Ignoring negative image cap %r", value)
        return None
    if number == 0:
        return 0  # explicit unlimited; distinct from missing (None)
    return number


def effective_caps(
    project_width: Optional[int],
    project_height: Optional[int],
    object_width: Optional[int],
    object_height: Optional[int],
) -> Tuple[Optional[int], Optional[int]]:
    """Per-object value (including 0) replaces that side; missing inherits project."""
    width = project_width
    height = project_height
    if object_width is not None:
        width = None if object_width == 0 else object_width
    if object_height is not None:
        height = None if object_height == 0 else object_height
    return width, height


def parse_embedded_image(style: Optional[str]) -> Optional[Tuple[str, str]]:
    """Return ``(type_token, base64_payload)`` from an mxCell style, or None."""
    if style is None or "image=data:image/" not in style:
        return None
    image_attrib = None
    for part in style.split(";"):
        if "image=data:image/" in part:
            image_attrib = part.split("image=data:image/")
            break
    if image_attrib is None or len(image_attrib) != 2:
        return None
    image_parts = image_attrib[1].split(",", 1)
    if len(image_parts) != 2:
        return None
    type_token = image_parts[0].split(";", 1)[0].strip().lower()
    payload = image_parts[1].strip()
    if not type_token or not payload:
        return None
    return type_token, payload


def _pillow_format(type_token: str) -> Optional[str]:
    if type_token in JPEG_TYPES:
        return "JPEG"
    if type_token == "jpg":
        return "JPEG"
    mapping = {
        "png": "PNG",
        "gif": "GIF",
        "webp": "WEBP",
        "bmp": "BMP",
        "tiff": "TIFF",
        "tif": "TIFF",
    }
    return mapping.get(type_token)


def maybe_resize_image(raw: bytes, type_token: str, max_width: Optional[int], max_height: Optional[int]) -> bytes:
    """Fit ``raw`` inside the box. Returns original bytes when no resize is needed."""
    if type_token in VECTOR_TYPES:
        return raw
    if not max_width and not max_height:
        return raw
    if Image is None:
        logger.warning("Pillow is not installed; leaving image at original size")
        return raw
    try:
        img = Image.open(io.BytesIO(raw))
    except Exception as exc:
        logger.warning("Could not decode image (%s); leaving original bytes: %s", type_token, exc)
        return raw
    if getattr(img, "is_animated", False) and getattr(img, "n_frames", 1) > 1:
        logger.warning("Animated %s image left at original size", type_token)
        return raw
    try:
        img = ImageOps.exif_transpose(img) or img
    except Exception:
        pass
    native_w, native_h = img.size
    if native_w <= 0 or native_h <= 0:
        return raw
    scale = 1.0
    if max_width:
        scale = min(scale, max_width / float(native_w))
    if max_height:
        scale = min(scale, max_height / float(native_h))
    if scale >= 1.0:
        return raw
    new_w = max(1, int(round(native_w * scale)))
    new_h = max(1, int(round(native_h * scale)))
    fmt = _pillow_format(type_token)
    if fmt is None:
        logger.warning("Unrecognized image type %s; leaving original bytes", type_token)
        return raw
    try:
        resized = img.resize((new_w, new_h), RESAMPLE)
        if fmt == "JPEG" and resized.mode not in ("RGB", "L"):
            resized = resized.convert("RGB")
        buf = io.BytesIO()
        save_kwargs = {}
        if fmt == "JPEG":
            save_kwargs = {"quality": 90, "optimize": True}
        resized.save(buf, format=fmt, **save_kwargs)
        out = buf.getvalue()
    except Exception as exc:
        logger.warning("Failed to resize %s image; leaving original bytes: %s", type_token, exc)
        return raw
    if fmt == "JPEG" and len(out) > len(raw):
        return raw
    return out


def write_image_file(media_path: str, type_token: str, data: bytes) -> Tuple[str, str]:
    """Write ``data`` under ``{media_path}/images/{md5}.{type}``. Return (basename, b64)."""
    images_dir = os.path.join(media_path, "images")
    os.makedirs(images_dir, exist_ok=True)
    digest = hashlib.md5(data).hexdigest()
    file_name = os.path.join(images_dir, f"{digest}.{type_token}")
    with open(file_name, "wb") as handle:
        handle.write(data)
    payload = base64.b64encode(data).decode("ascii")
    return os.path.basename(file_name), payload


def object_image_caps(object_elm) -> Tuple[Optional[int], Optional[int]]:
    if object_elm is None:
        return None, None
    attrib: Mapping[str, Any] = getattr(object_elm, "attrib", {}) or {}
    return parse_max_attr(attrib.get("max_width")), parse_max_attr(attrib.get("max_height"))
