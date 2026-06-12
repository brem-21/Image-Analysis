from tests.conftest import API


def test_register_and_login(client):
    r = client.post(f"{API}/auth/register", json={"email": "a@test.com", "password": "password123"})
    assert r.status_code == 201
    assert r.json()["email"] == "a@test.com"

    tok = client.post(f"{API}/auth/login", json={"email": "a@test.com", "password": "password123"})
    assert tok.status_code == 200
    body = tok.json()
    assert body["access_token"] and body["refresh_token"]


def test_duplicate_email_rejected(client):
    client.post(f"{API}/auth/register", json={"email": "dup@test.com", "password": "password123"})
    r = client.post(f"{API}/auth/register", json={"email": "dup@test.com", "password": "password123"})
    assert r.status_code == 409


def test_wrong_password_rejected(client):
    client.post(f"{API}/auth/register", json={"email": "w@test.com", "password": "password123"})
    r = client.post(f"{API}/auth/login", json={"email": "w@test.com", "password": "nope"})
    assert r.status_code == 401


def test_me_requires_token(client, auth_headers):
    assert client.get(f"{API}/auth/me").status_code == 403
    r = client.get(f"{API}/auth/me", headers=auth_headers)
    assert r.status_code == 200 and r.json()["email"] == "u@test.com"


def test_refresh_returns_new_tokens(client):
    client.post(f"{API}/auth/register", json={"email": "r@test.com", "password": "password123"})
    tok = client.post(f"{API}/auth/login", json={"email": "r@test.com", "password": "password123"}).json()
    r = client.post(f"{API}/auth/refresh", json={"refresh_token": tok["refresh_token"]})
    assert r.status_code == 200 and r.json()["access_token"]


def test_access_token_not_valid_for_refresh(client):
    client.post(f"{API}/auth/register", json={"email": "x@test.com", "password": "password123"})
    tok = client.post(f"{API}/auth/login", json={"email": "x@test.com", "password": "password123"}).json()
    # Passing an access token where a refresh token is expected must fail.
    r = client.post(f"{API}/auth/refresh", json={"refresh_token": tok["access_token"]})
    assert r.status_code == 401


def test_login_rate_limited(client, monkeypatch):
    monkeypatch.setattr(ratelimit_settings(), "login_max_attempts", 3)
    ratelimit_limiter().clear()
    client.post(f"{API}/auth/register", json={"email": "rl@test.com", "password": "password123"})
    codes = [
        client.post(f"{API}/auth/login", json={"email": "rl@test.com", "password": "bad"}).status_code
        for _ in range(5)
    ]
    assert 429 in codes
    assert codes[:3] == [401, 401, 401]


# --- helpers (kept out of fixtures to keep the rate-limit test self-contained) ---
def ratelimit_settings():
    from app.core import ratelimit
    return ratelimit.settings


def ratelimit_limiter():
    from app.core import ratelimit
    return ratelimit._limiter._hits
