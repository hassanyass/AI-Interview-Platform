"""Supabase Storage adapter over its REST API (used for candidate CVs)."""
from __future__ import annotations

import asyncio
import logging

import httpx

from backend.providers.storage.base import ObjectStorage, StorageError, StorageUnavailable


logger = logging.getLogger(__name__)


class SupabaseStorage(ObjectStorage):
    def __init__(
        self,
        *,
        project_url: str,
        service_key: str,
        bucket: str,
        timeout_seconds: float = 30.0,
        retry_attempts: int = 2,
    ) -> None:
        self._base = f"{project_url}/storage/v1/object/{bucket}"
        self._headers = {"Authorization": f"Bearer {service_key}", "apikey": service_key}
        self._timeout = timeout_seconds
        self._retry_attempts = max(0, retry_attempts)
        self._configured = bool(project_url and service_key and bucket)

    async def _send(self, method: str, url: str, **kwargs) -> httpx.Response:
        """One request, retried on transport errors only (connection reset,
        timeout). A 4xx/5xx answer is returned to the caller unretried --
        the store spoke; PUT carries x-upsert so a repeat is safe."""
        attempt = 0
        while True:
            try:
                async with httpx.AsyncClient(timeout=self._timeout) as client:
                    return await client.request(method, url, **kwargs)
            except httpx.TransportError as e:
                if attempt >= self._retry_attempts:
                    raise StorageUnavailable(f"Supabase Storage unreachable: {e}") from e
                attempt += 1
                logger.warning("Supabase Storage %s %s transport error (%s); retry %d/%d",
                               method, url, e, attempt, self._retry_attempts)
                await asyncio.sleep(0.5 * attempt)

    @property
    def configured(self) -> bool:
        return self._configured

    async def put(self, key: str, data: bytes, *, content_type: str) -> None:
        resp = await self._send(
            "POST",
            f"{self._base}/{key}",
            # x-upsert lets a retried request succeed instead of 409ing
            # on its own half-written object.
            headers={**self._headers, "Content-Type": content_type, "x-upsert": "true"},
            content=data,
        )
        if resp.status_code not in (200, 201):
            raise StorageError(
                f"Supabase Storage upload failed ({resp.status_code}) for {key}: {resp.text[:300]}",
                status_code=resp.status_code,
            )

    async def delete(self, key: str) -> None:
        resp = await self._send("DELETE", f"{self._base}/{key}", headers=self._headers)
        if resp.status_code not in (200, 204):
            raise StorageError(
                f"Supabase Storage delete failed ({resp.status_code}) for {key}",
                status_code=resp.status_code,
            )

    def presign_get(self, key: str, *, ttl_seconds: int) -> str:
        raise NotImplementedError("Supabase Storage presigned URLs are not used by the backend")
