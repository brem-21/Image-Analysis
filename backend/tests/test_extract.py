import app.routers.extract as extract_router
from tests.conftest import API


def _fake_result(**values):
    base = {"item_name": "KIVO 70G SACHET", "barcode": "4006381333931", "brand": "Kivo"}
    base.update(values)
    return {
        "values": base,
        "confidence": {"brand": 0.9},
        "source": {"brand": "vlm"},
        "needs_review": False,
        "vlm_error": None,
    }


def test_extract_creates_records(client, auth_headers, jpeg_bytes, monkeypatch):
    monkeypatch.setattr(extract_router, "run_pipeline", lambda *a, **k: _fake_result())
    r = client.post(
        f"{API}/extract",
        headers=auth_headers,
        files=[("files", ("a.jpg", jpeg_bytes, "image/jpeg"))],
        data={"label": "batch-1"},
    )
    assert r.status_code == 201
    body = r.json()
    assert body["session_id"]
    rec = body["records"][0]
    assert rec["brand"] == "Kivo"
    assert rec["item_name"] == "KIVO 70G SACHET"
    assert rec["source"]["brand"] == "vlm"
    assert rec["vlm_error"] is None


def test_extract_requires_auth(client, jpeg_bytes):
    r = client.post(f"{API}/extract", files=[("files", ("a.jpg", jpeg_bytes, "image/jpeg"))])
    assert r.status_code == 403


def test_extract_rejects_bad_content_type(client, auth_headers):
    r = client.post(
        f"{API}/extract",
        headers=auth_headers,
        files=[("files", ("a.txt", b"hello", "text/plain"))],
    )
    assert r.status_code == 415


def test_extract_rejects_too_many_files(client, auth_headers, jpeg_bytes):
    files = [("files", (f"{i}.jpg", jpeg_bytes, "image/jpeg")) for i in range(21)]
    r = client.post(f"{API}/extract", headers=auth_headers, files=files)
    assert r.status_code == 413


def test_extract_surfaces_vlm_error(client, auth_headers, jpeg_bytes, monkeypatch):
    monkeypatch.setattr(
        extract_router, "run_pipeline",
        lambda *a, **k: _fake_result() | {"vlm_error": "ServerError: 503 UNAVAILABLE"},
    )
    r = client.post(
        f"{API}/extract", headers=auth_headers,
        files=[("files", ("a.jpg", jpeg_bytes, "image/jpeg"))],
    )
    assert r.status_code == 201
    assert r.json()["records"][0]["vlm_error"] == "ServerError: 503 UNAVAILABLE"
