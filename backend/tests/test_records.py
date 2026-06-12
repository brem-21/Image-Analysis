from tests.conftest import API


def test_list_empty(client, auth_headers):
    assert client.get(f"{API}/records", headers=auth_headers).json() == []


def test_list_pagination_and_total_header(client, auth_headers, seed):
    for i in range(5):
        seed(item_name=f"ITEM {i}", brand="Kivo")
    r = client.get(f"{API}/records?limit=2&offset=0", headers=auth_headers)
    assert r.status_code == 200
    assert len(r.json()) == 2
    assert r.headers["X-Total-Count"] == "5"


def test_list_filters(client, auth_headers, seed):
    seed(item_name="A", brand="Kivo", needs_review=True)
    seed(item_name="B", brand="Pepsi", needs_review=False)
    only_kivo = client.get(f"{API}/records?brand=Kivo", headers=auth_headers).json()
    assert [r["brand"] for r in only_kivo] == ["Kivo"]
    flagged = client.get(f"{API}/records?needs_review=true", headers=auth_headers).json()
    assert all(r["needs_review"] for r in flagged) and len(flagged) == 1


def test_patch_regenerates_item_name_and_marks_human(client, auth_headers, seed):
    rid = seed(item_name="OLD", brand="Kivo", weight_value=70, weight_unit="g", packaging_type="Sachet")
    r = client.patch(f"{API}/records/{rid}", headers=auth_headers, json={"variant_type": "Classic"})
    assert r.status_code == 200
    body = r.json()
    assert body["variant_type"] == "Classic"
    assert body["source"]["variant_type"] == "human"
    # item_name regenerated from fields (not the stale "OLD").
    assert "KIVO" in body["item_name"] and "CLASSIC" in body["item_name"]


def test_patch_explicit_item_name_is_kept(client, auth_headers, seed):
    rid = seed(item_name="OLD", brand="Kivo")
    r = client.patch(f"{API}/records/{rid}", headers=auth_headers, json={"item_name": "MY CUSTOM NAME"})
    assert r.json()["item_name"] == "MY CUSTOM NAME"


def test_delete_record(client, auth_headers, seed):
    rid = seed(item_name="X", brand="Kivo")
    assert client.delete(f"{API}/records/{rid}", headers=auth_headers).status_code == 204
    assert client.get(f"{API}/records", headers=auth_headers).json() == []


def test_records_are_user_scoped(client, auth_headers, seed):
    rid = seed(item_name="MINE", brand="Kivo")
    # A second user must not see or touch the first user's record.
    client.post(f"{API}/auth/register", json={"email": "other@test.com", "password": "password123"})
    tok = client.post(f"{API}/auth/login", json={"email": "other@test.com", "password": "password123"}).json()
    other = {"Authorization": f"Bearer {tok['access_token']}"}
    assert client.get(f"{API}/records", headers=other).json() == []
    assert client.patch(f"{API}/records/{rid}", headers=other, json={"brand": "Hijack"}).status_code == 404
    assert client.delete(f"{API}/records/{rid}", headers=other).status_code == 404
