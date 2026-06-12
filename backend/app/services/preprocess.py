"""Light image preprocessing: downscale large images and normalize to JPEG.

Keeps payloads small for the VLM while preserving label legibility.
"""
from __future__ import annotations

import io

from PIL import Image, ImageOps

MAX_DIM = 1600


def preprocess(image_bytes: bytes) -> bytes:
    img = Image.open(io.BytesIO(image_bytes))
    img = ImageOps.exif_transpose(img)  # honor camera orientation
    img = img.convert("RGB")

    if max(img.size) > MAX_DIM:
        img.thumbnail((MAX_DIM, MAX_DIM), Image.LANCZOS)

    out = io.BytesIO()
    img.save(out, format="JPEG", quality=90)
    return out.getvalue()
