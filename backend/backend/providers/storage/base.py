"""Object-storage port. Two stores exist today: CVs in Supabase Storage,
interview recordings in Cloudflare R2 (written by LiveKit Egress, read and
deleted by the backend)."""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass


class StorageError(Exception):
    """The store answered, but refused (4xx/5xx)."""

    def __init__(self, message: str, *, status_code: int | None = None) -> None:
        super().__init__(message)
        self.status_code = status_code


class StorageUnavailable(StorageError):
    """The store could not be reached at all."""


@dataclass(frozen=True)
class S3Destination:
    """What an external writer (LiveKit Egress) needs to upload straight
    into an S3-compatible bucket."""
    access_key: str
    secret: str
    bucket: str
    endpoint: str
    region: str = "auto"
    force_path_style: bool = True


class ObjectStorage(ABC):
    @property
    @abstractmethod
    def configured(self) -> bool:
        """False when the credentials for this store are absent; callers
        keep their existing 'not configured -> skip' behaviour."""

    @abstractmethod
    async def put(self, key: str, data: bytes, *, content_type: str) -> None:
        """Create or overwrite ``key``. Raises StorageError."""

    @abstractmethod
    async def delete(self, key: str) -> None:
        """Delete ``key``. Raises StorageError; deleting a missing key is not an error."""

    @abstractmethod
    def presign_get(self, key: str, *, ttl_seconds: int) -> str:
        """Short-lived GET URL for ``key``. Raises NotImplementedError where the store cannot."""

    def egress_destination(self) -> S3Destination:
        """Upload target for an external S3 writer. Only S3-compatible stores support it."""
        raise NotImplementedError(f"{type(self).__name__} cannot be written to by an external S3 client")
