"""Deterministic barcode decoding + check-digit validation.

VLMs hallucinate barcode digits, so we never trust the model for this field.
We decode with pyzbar (zbar) and validate the EAN-13 / UPC-A check digit.
"""
from __future__ import annotations

import io

import numpy as np
from PIL import Image

try:
    from pyzbar.pyzbar import decode as _zbar_decode

    _ZBAR_AVAILABLE = True
except Exception:  # pragma: no cover - zbar shared lib may be missing on some hosts
    _ZBAR_AVAILABLE = False


def validate_ean13(code: str) -> bool:
    if not (code.isdigit() and len(code) == 13):
        return False
    digits = [int(c) for c in code]
    checksum = sum(d * (3 if i % 2 else 1) for i, d in enumerate(digits[:12]))
    check_digit = (10 - (checksum % 10)) % 10
    return check_digit == digits[12]


def validate_upca(code: str) -> bool:
    if not (code.isdigit() and len(code) == 12):
        return False
    digits = [int(c) for c in code]
    checksum = sum(d * (3 if i % 2 == 0 else 1) for i, d in enumerate(digits[:11]))
    check_digit = (10 - (checksum % 10)) % 10
    return check_digit == digits[11]


def is_valid_barcode(code: str | None) -> bool:
    if not code:
        return False
    return validate_ean13(code) or validate_upca(code)


def decode_barcode(image_bytes: bytes) -> tuple[str | None, float]:
    """Return (barcode, confidence). Confidence is 0.99 if the check digit
    validates, 0.6 if decoded but checksum unknown, 0.0 if nothing found.
    """
    if not _ZBAR_AVAILABLE:
        return None, 0.0

    try:
        img = Image.open(io.BytesIO(image_bytes)).convert("RGB")
    except Exception:
        return None, 0.0

    results = _zbar_decode(np.array(img))
    for r in results:
        code = r.data.decode("utf-8", errors="ignore")
        if is_valid_barcode(code):
            return code, 0.99
    # Fall back to first decoded value even if checksum type is unknown.
    if results:
        return results[0].data.decode("utf-8", errors="ignore"), 0.6
    return None, 0.0
