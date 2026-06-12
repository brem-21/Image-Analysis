from tests.conftest import API


def test_dedup_exact_barcode(client, auth_headers, seed):
    seed(item_name="KIVO A", barcode="4006381333931", brand="Kivo")
    seed(item_name="KIVO B", barcode="4006381333931", brand="Kivo")
    r = client.post(f"{API}/records/dedup", headers=auth_headers)
    cands = r.json()["candidates"]
    assert len(cands) == 1
    assert cands[0]["score"] == 1.0
    assert cands[0]["reason"] == "Identical barcode"


def test_dedup_fuzzy_brand_and_name(client, auth_headers, seed):
    seed(item_name="KIVO TOMATO 70G SACHET", brand="Kivo", weight_value=70, weight_unit="g")
    seed(item_name="KIVO TOMATO 70G SACHETT", brand="Kivo", weight_value=70, weight_unit="g")
    cands = client.post(f"{API}/records/dedup", headers=auth_headers).json()["candidates"]
    assert len(cands) == 1
    assert "item_name" in cands[0]["matched_fields"]


def test_no_duplicates_for_distinct_products(client, auth_headers, seed):
    seed(item_name="KIVO TOMATO", brand="Kivo", barcode="4006381333931")
    seed(item_name="PEPSI COLA", brand="Pepsi", barcode="036000291452")
    assert client.post(f"{API}/records/dedup", headers=auth_headers).json()["candidates"] == []


def test_merge_fills_gaps_and_deletes_other(client, auth_headers, seed):
    keep = seed(item_name="KIVO", brand="Kivo", barcode="4006381333931")
    dup = seed(item_name="KIVO", brand="Kivo", barcode="4006381333931",
               manufacturer="Green Field FZC", source={"manufacturer": "vlm"},
               confidence={"manufacturer": 0.8})
    r = client.post(f"{API}/records/merge", headers=auth_headers, json={"keep_id": keep, "merge_id": dup})
    assert r.status_code == 200
    body = r.json()
    assert body["id"] == keep
    assert body["manufacturer"] == "Green Field FZC"  # gap filled from merged record
    # Only one record remains.
    assert len(client.get(f"{API}/records", headers=auth_headers).json()) == 1
