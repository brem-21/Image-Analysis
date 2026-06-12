import io

from tests.conftest import API

OFFICIAL_HEADER = (
    "ITEM_NAME,BARCODE,MANUFACTURER,BRAND,WEIGHT,PACKAGING_TYPE,COUNTRY,"
    "VARIANT_TYPE,FRAGRANCE_FLAVOR,PROMOTION,ADDONS,TAGLINE"
)


def test_csv_header_matches_target_exactly(client, auth_headers, seed):
    seed(item_name="KIVO 70G SACHET", barcode="4006381333931", brand="Kivo",
         weight_value=70, weight_unit="g", packaging_type="Sachet")
    r = client.get(f"{API}/export?format=csv", headers=auth_headers)
    assert r.status_code == 200
    lines = r.content.decode().splitlines()
    assert lines[0] == OFFICIAL_HEADER
    # WEIGHT rendered as a single string.
    assert "70G" in lines[1]


def test_csv_include_meta_appends_extras(client, auth_headers, seed):
    seed(item_name="X", brand="Kivo", category_type="Condiments")
    r = client.get(f"{API}/export?format=csv&include_meta=true", headers=auth_headers)
    header = r.content.decode().splitlines()[0]
    assert header == OFFICIAL_HEADER + ",CATEGORY_TYPE,NEEDS_REVIEW"


def test_xlsx_export_returns_workbook(client, auth_headers, seed):
    seed(item_name="X", brand="Kivo")
    r = client.get(f"{API}/export?format=xlsx", headers=auth_headers)
    assert r.status_code == 200
    # XLSX is a zip archive — starts with the PK magic bytes.
    assert r.content[:2] == b"PK"


def test_export_invalid_format_rejected(client, auth_headers):
    assert client.get(f"{API}/export?format=pdf", headers=auth_headers).status_code == 422
