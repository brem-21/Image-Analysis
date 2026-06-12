"""Minimal in-memory fixed-window rate limiter.

Good enough for a single-process deployment / demo. NOTE: state is per-process,
so it does not coordinate across multiple workers — swap for Redis when scaling.
"""
from __future__ import annotations

import threading
import time

from fastapi import HTTPException, Request, status

from app.config import settings


class _FixedWindowLimiter:
    def __init__(self) -> None:
        self._hits: dict[str, list[float]] = {}
        self._lock = threading.Lock()

    def check(self, key: str, max_attempts: int, window_seconds: int) -> None:
        now = time.time()
        cutoff = now - window_seconds
        with self._lock:
            timestamps = [t for t in self._hits.get(key, []) if t > cutoff]
            if len(timestamps) >= max_attempts:
                retry_after = int(window_seconds - (now - timestamps[0])) + 1
                raise HTTPException(
                    status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                    detail="Too many attempts. Please try again later.",
                    headers={"Retry-After": str(max(retry_after, 1))},
                )
            timestamps.append(now)
            self._hits[key] = timestamps


_limiter = _FixedWindowLimiter()


def _client_ip(request: Request) -> str:
    forwarded = request.headers.get("x-forwarded-for")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.client.host if request.client else "unknown"


def login_rate_limit(request: Request) -> None:
    """FastAPI dependency: throttle login attempts per client IP."""
    _limiter.check(
        key=f"login:{_client_ip(request)}",
        max_attempts=settings.login_max_attempts,
        window_seconds=settings.login_window_seconds,
    )
