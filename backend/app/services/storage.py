"""S3 image storage service.

Uploads are fire-and-forget from the caller's perspective — extraction
proceeds even if S3 is unavailable (s3_key on the record will be None).
"""
from __future__ import annotations

import asyncio
import logging
from functools import lru_cache

import boto3
from botocore.exceptions import BotoCoreError, ClientError

from app.config import settings

logger = logging.getLogger(__name__)


@lru_cache(maxsize=1)
def _client():
    return boto3.client(
        "s3",
        region_name=settings.aws_region,
        aws_access_key_id=settings.aws_access_key_id or None,
        aws_secret_access_key=settings.aws_secret_access_key or None,
    )


def _upload_sync(key: str, data: bytes, content_type: str) -> None:
    _client().put_object(
        Bucket=settings.s3_bucket,
        Key=key,
        Body=data,
        ContentType=content_type,
    )


async def upload_image(
    key: str,
    data: bytes,
    content_type: str = "image/jpeg",
) -> str | None:
    """Upload *data* to S3 at *key*. Returns the key on success, None on failure."""
    if not settings.s3_enabled:
        logger.debug("S3 not configured — skipping upload for %s", key)
        return None
    try:
        loop = asyncio.get_running_loop()
        await loop.run_in_executor(None, _upload_sync, key, data, content_type)
        logger.info("Uploaded %s to s3://%s/%s", key, settings.s3_bucket, key)
        return key
    except (BotoCoreError, ClientError) as exc:
        logger.error("S3 upload failed for %s: %s", key, exc)
        return None


def s3_key(user_id: int, session_id: int, filename: str) -> str:
    """Deterministic key: uploads/{user_id}/{session_id}/{filename}"""
    safe = "".join(c if c.isalnum() or c in "._-" else "_" for c in filename)
    return f"{settings.s3_prefix}/{user_id}/{session_id}/{safe}"
