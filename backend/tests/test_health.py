def test_health_ok(client):
    r = client.get("/health")
    assert r.status_code == 200
    assert r.json() == {"status": "ok", "database": "ok"}


def test_health_is_at_root_not_under_prefix(client):
    # /health is intentionally outside /api/v1 for probes.
    assert client.get("/api/v1/health").status_code == 404
