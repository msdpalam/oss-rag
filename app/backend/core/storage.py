"""
MinIO / S3-compatible object storage async wrapper.
Uses boto3 in a thread pool to avoid blocking the event loop.
"""
import asyncio
from concurrent.futures import ThreadPoolExecutor
from typing import Optional

import structlog

from core.config import settings

log = structlog.get_logger()


class StorageService:

    def __init__(self) -> None:
        self._client = None
        self._executor = ThreadPoolExecutor(max_workers=4, thread_name_prefix="storage")

    @property
    def client(self):
        if self._client is None:
            import boto3

            kwargs: dict = {
                "aws_access_key_id": settings.S3_ACCESS_KEY,
                "aws_secret_access_key": settings.S3_SECRET_KEY,
                "region_name": settings.S3_REGION,
            }
            if settings.S3_ENDPOINT_URL:
                kwargs["endpoint_url"] = settings.S3_ENDPOINT_URL
            self._client = boto3.client("s3", **kwargs)
        return self._client

    async def upload(
        self,
        bucket: str,
        key: str,
        data: bytes,
        content_type: str = "application/octet-stream",
    ) -> str:
        loop = asyncio.get_event_loop()
        await loop.run_in_executor(
            self._executor,
            lambda: self.client.put_object(
                Bucket=bucket, Key=key, Body=data, ContentType=content_type
            ),
        )
        log.debug("storage.uploaded", bucket=bucket, key=key, size=len(data))
        return key

    async def download(self, bucket: str, key: str) -> bytes:
        loop = asyncio.get_event_loop()
        response = await loop.run_in_executor(
            self._executor,
            lambda: self.client.get_object(Bucket=bucket, Key=key),
        )
        return response["Body"].read()

    async def delete(self, bucket: str, key: str) -> None:
        loop = asyncio.get_event_loop()
        await loop.run_in_executor(
            self._executor,
            lambda: self.client.delete_object(Bucket=bucket, Key=key),
        )
        log.debug("storage.deleted", bucket=bucket, key=key)

    async def get_presigned_url(
        self, bucket: str, key: str, expiry: int = 3600
    ) -> str:
        loop = asyncio.get_event_loop()
        url = await loop.run_in_executor(
            self._executor,
            lambda: self.client.generate_presigned_url(
                "get_object",
                Params={"Bucket": bucket, "Key": key},
                ExpiresIn=expiry,
            ),
        )
        return url


storage = StorageService()
