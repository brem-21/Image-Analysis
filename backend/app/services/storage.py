"""Source-image storage. Local filesystem for now; swap the body of these
functions for S3/GCS later without touching callers."""
from __future__ import annotations

import os

from app.config import settings

_EXT = {"image/jpeg": "jpg", "image/png": "png", "image/webp": "webp"}


def _dir() -> str:
    os.makedirs(settings.upload_dir, exist_ok=True)
    return settings.upload_dir


def save_image(record_id: int, data: bytes, content_type: str | None) -> str:
    """Persist the bytes and return the stored filename."""
    ext = _EXT.get((content_type or "").lower(), "jpg")
    filename = f"{record_id}.{ext}"
    with open(os.path.join(_dir(), filename), "wb") as fh:
        fh.write(data)
    return filename


def image_path(filename: str) -> str:
    return os.path.join(settings.upload_dir, filename)


def read_image(filename: str) -> bytes:
    with open(image_path(filename), "rb") as fh:
        return fh.read()


def image_exists(filename: str | None) -> bool:
    return bool(filename) and os.path.exists(image_path(filename))


def delete_image(filename: str | None) -> None:
    if not filename:
        return
    try:
        os.remove(image_path(filename))
    except OSError:
        pass


def media_type(filename: str) -> str:
    ext = filename.rsplit(".", 1)[-1].lower()
    return {"jpg": "image/jpeg", "png": "image/png", "webp": "image/webp"}.get(ext, "application/octet-stream")
