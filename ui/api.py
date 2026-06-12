"""Thin HTTP client for the Image-to-IMDB backend."""
from __future__ import annotations

import requests


class APIError(Exception):
    def __init__(self, status: int, detail: str):
        self.status = status
        self.detail = detail
        super().__init__(f"{status}: {detail}")


API_PREFIX = "/api/v1"


class IMDBClient:
    def __init__(self, base_url: str, token: str | None = None, timeout: float = 120.0):
        self.root_url = base_url.rstrip("/")
        self.base_url = self.root_url + API_PREFIX
        self.token = token
        self.timeout = timeout

    # --- internals -------------------------------------------------------
    def _headers(self, auth: bool = True) -> dict:
        h = {}
        if auth and self.token:
            h["Authorization"] = f"Bearer {self.token}"
        return h

    def _handle(self, resp: requests.Response):
        if resp.status_code >= 400:
            try:
                detail = resp.json().get("detail", resp.text)
            except Exception:
                detail = resp.text
            raise APIError(resp.status_code, str(detail))
        if resp.headers.get("content-type", "").startswith("application/json"):
            return resp.json()
        return resp.content

    # --- auth ------------------------------------------------------------
    def register(self, email: str, password: str):
        r = requests.post(f"{self.base_url}/auth/register",
                          json={"email": email, "password": password}, timeout=self.timeout)
        return self._handle(r)

    def login(self, email: str, password: str) -> dict:
        r = requests.post(f"{self.base_url}/auth/login",
                          json={"email": email, "password": password}, timeout=self.timeout)
        data = self._handle(r)
        self.token = data["access_token"]
        return data

    def me(self):
        return self._handle(requests.get(f"{self.base_url}/auth/me",
                                        headers=self._headers(), timeout=self.timeout))

    # --- pipeline --------------------------------------------------------
    def extract(self, files: list[tuple[str, bytes, str]], label: str = "") -> dict:
        """files: list of (filename, content_bytes, mime_type)."""
        multipart = [("files", (name, data, mime)) for name, data, mime in files]
        r = requests.post(f"{self.base_url}/extract", headers=self._headers(),
                          files=multipart, data={"label": label}, timeout=self.timeout)
        return self._handle(r)

    def list_records(self, **filters) -> list[dict]:
        params = {k: v for k, v in filters.items() if v not in (None, "", "All")}
        return self._handle(requests.get(f"{self.base_url}/records",
                                        headers=self._headers(), params=params, timeout=self.timeout))

    def update_record(self, record_id: int, payload: dict) -> dict:
        return self._handle(requests.patch(f"{self.base_url}/records/{record_id}",
                                          headers=self._headers(), json=payload, timeout=self.timeout))

    def delete_record(self, record_id: int):
        return self._handle(requests.delete(f"{self.base_url}/records/{record_id}",
                                           headers=self._headers(), timeout=self.timeout))

    def dedup(self, session_id: int | None = None) -> dict:
        params = {"session_id": session_id} if session_id else {}
        return self._handle(requests.post(f"{self.base_url}/records/dedup",
                                         headers=self._headers(), params=params, timeout=self.timeout))

    def merge(self, keep_id: int, merge_id: int) -> dict:
        return self._handle(requests.post(f"{self.base_url}/records/merge",
                                         headers=self._headers(),
                                         json={"keep_id": keep_id, "merge_id": merge_id}, timeout=self.timeout))

    def export(self, fmt: str = "csv", session_id: int | None = None) -> bytes:
        params = {"format": fmt}
        if session_id:
            params["session_id"] = session_id
        return self._handle(requests.get(f"{self.base_url}/export",
                                        headers=self._headers(), params=params, timeout=self.timeout))

    def health(self) -> dict:
        return self._handle(requests.get(f"{self.root_url}/health", timeout=self.timeout))
