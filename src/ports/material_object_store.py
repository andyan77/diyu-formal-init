from __future__ import annotations

from abc import ABC, abstractmethod
from uuid import UUID


class MaterialObjectStore(ABC):
    """Stores raw user-selected references outside relational metadata."""

    @abstractmethod
    def put(self, asset_id: UUID, suffix: str, payload: bytes) -> str:
        """Persist an original reference file and return its opaque object key."""

    @abstractmethod
    def get(self, object_key: str) -> bytes:
        """Read back one already-authorized object; callers must check scope first."""

    @abstractmethod
    def delete(self, object_key: str) -> None:
        """Remove one previously authorized object; missing objects are harmless."""
