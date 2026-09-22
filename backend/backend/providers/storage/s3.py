"""S3-compatible adapter (Cloudflare R2 today). boto3 is synchronous: the
network calls (put/delete) run in a worker thread (H2-B) so they never block
the event loop; presign is pure local signing and stays inline."""
from __future__ import annotations

import asyncio

import boto3
from botocore.config import Config

from backend.providers.storage.base import ObjectStorage, S3Destination, StorageError


class S3CompatibleStorage(ObjectStorage):
    def __init__(
        self,
        *,
        endpoint: str,
        access_key_id: str,
        secret_access_key: str,
        bucket: str,
        account_id: str = "",
        connect_timeout: float = 5.0,
        read_timeout: float = 30.0,
        max_attempts: int = 3,
    ) -> None:
        self._connect_timeout = connect_timeout
        self._read_timeout = read_timeout
        self._max_attempts = max_attempts
        self._endpoint = endpoint
        self._access_key_id = access_key_id
        self._secret_access_key = secret_access_key
        self._bucket = bucket
        self._account_id = account_id
        self._client = None

    @property
    def configured(self) -> bool:
        return all([self._account_id, self._access_key_id, self._secret_access_key, self._bucket, self._endpoint])

    def _s3(self):
        if self._client is None:
            # region "auto", SigV4 and path-style addressing are what R2
            # requires; they must also match what LiveKit Egress uses to
            # write the object (S3Destination.force_path_style).
            self._client = boto3.client(
                "s3",
                endpoint_url=self._endpoint,
                aws_access_key_id=self._access_key_id,
                aws_secret_access_key=self._secret_access_key,
                region_name="auto",
                config=Config(
                    signature_version="s3v4",
                    s3={"addressing_style": "path"},
                    connect_timeout=self._connect_timeout,
                    read_timeout=self._read_timeout,
                    retries={"max_attempts": self._max_attempts, "mode": "standard"},
                ),
            )
        return self._client

    async def put(self, key: str, data: bytes, *, content_type: str) -> None:
        try:
            await asyncio.to_thread(
                self._s3().put_object, Bucket=self._bucket, Key=key, Body=data, ContentType=content_type
            )
        except Exception as e:  # noqa: BLE001 -- botocore raises assorted classes; callers see one StorageError
            raise StorageError(f"put {key!r} failed: {e}") from e

    async def delete(self, key: str) -> None:
        try:
            await asyncio.to_thread(self._s3().delete_object, Bucket=self._bucket, Key=key)
        except Exception as e:  # noqa: BLE001 -- same translation as put()
            raise StorageError(f"delete {key!r} failed: {e}") from e

    def presign_get(self, key: str, *, ttl_seconds: int) -> str:
        return self._s3().generate_presigned_url(
            "get_object",
            Params={"Bucket": self._bucket, "Key": key},
            ExpiresIn=ttl_seconds,
        )

    def egress_destination(self) -> S3Destination:
        return S3Destination(
            access_key=self._access_key_id,
            secret=self._secret_access_key,
            bucket=self._bucket,
            endpoint=self._endpoint,
        )
