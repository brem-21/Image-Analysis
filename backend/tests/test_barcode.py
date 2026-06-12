from app.services import barcode as B


def test_validate_ean13():
    assert B.validate_ean13("4006381333931") is True   # known valid EAN-13
    assert B.validate_ean13("4006381333930") is False   # bad check digit
    assert B.validate_ean13("12345") is False           # wrong length


def test_validate_upca():
    assert B.validate_upca("036000291452") is True       # known valid UPC-A
    assert B.validate_upca("036000291453") is False       # bad check digit


def test_is_valid_barcode():
    assert B.is_valid_barcode("4006381333931") is True
    assert B.is_valid_barcode(None) is False
    assert B.is_valid_barcode("not-a-barcode") is False


def test_decode_blank_image_returns_none(jpeg_bytes):
    # A blank image has no barcode; must degrade gracefully (no exception),
    # whether or not the native ZBar library is present.
    code, conf = B.decode_barcode(jpeg_bytes)
    assert code is None and conf == 0.0
