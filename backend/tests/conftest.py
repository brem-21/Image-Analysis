"""Shared test fixtures.

Environment is configured BEFORE importing the app so settings/engine pick up
the test database and a real JWT secret. The VLM is never called for real —
extract tests monkeypatch the pipeline, and pipeline tests monkeypatch the
Gemini extractor.
"""
import io
import os

# --- must run before any `app.*` import ---
os.environ.setdefault("DATABASE_URL", "sqlite:///./test_run.db")
os.environ.setdefault("JWT_SECRET", "test-secret-0123456789-abcdefghij")
os.environ.setdefault("GEMINI_API_KEY", "")  # force VLM to be mocked
os.environ.setdefault("ENVIRONMENT", "development")
os.environ.setdefault("LOGIN_MAX_ATTEMPTS", "100")  # avoid cross-test interference
os.environ.setdefault("LOGIN_WINDOW_SECONDS", "60")

import pytest
from fastapi.testclient import TestClient
from PIL import Image

from app.core import ratelimit
from app.database import Base, engine
from app.main import app

API = "/api/v1"


@pytest.fixture(autouse=True)
def _fresh_state():
    """Each test starts with empty tables and a clean rate limiter."""
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)
    ratelimit._limiter._hits.clear()
    yield
    Base.metadata.drop_all(bind=engine)


@pytest.fixture
def client():
    with TestClient(app) as c:
        yield c


@pytest.fixture
def auth_headers(client):
    client.post(f"{API}/auth/register", json={"email": "u@test.com", "password": "password123"})
    tok = client.post(f"{API}/auth/login", json={"email": "u@test.com", "password": "password123"}).json()
    return {"Authorization": f"Bearer {tok['access_token']}"}


@pytest.fixture
def jpeg_bytes() -> bytes:
    buf = io.BytesIO()
    Image.new("RGB", (64, 64), "white").save(buf, format="JPEG")
    return buf.getvalue()


@pytest.fixture
def seed(auth_headers):
    """Factory: insert an ItemRecord for the authenticated user; returns its id."""
    from sqlalchemy import select

    from app.database import SessionLocal
    from app.models import ExtractionSession, ItemRecord, User

    def _seed(**fields):
        db = SessionLocal()
        try:
            uid = db.scalar(select(User).where(User.email == "u@test.com")).id
            sess = db.scalar(select(ExtractionSession).where(ExtractionSession.user_id == uid))
            if sess is None:
                sess = ExtractionSession(user_id=uid, label="t")
                db.add(sess)
                db.flush()
            rec = ItemRecord(
                user_id=uid,
                session_id=sess.id,
                confidence=fields.pop("confidence", {}),
                source=fields.pop("source", {}),
                needs_review=fields.pop("needs_review", False),
                **fields,
            )
            db.add(rec)
            db.commit()
            db.refresh(rec)
            return rec.id
        finally:
            db.close()

    return _seed
