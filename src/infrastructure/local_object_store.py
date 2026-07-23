from __future__ import annotations

import os
from pathlib import Path
from uuid import UUID

from src.ports.material_object_store import MaterialObjectStore


class LocalObjectStore(MaterialObjectStore):
    """Development/CI-only object store implementation behind the production port."""

    def __init__(self, root: str) -> None:
        self._root = Path(root).resolve()

    def put(self, asset_id: UUID, suffix: str, payload: bytes) -> str:
        normalized_suffix = suffix.lower() if suffix.startswith(".") else ""
        if normalized_suffix not in {
            ".txt",
            ".md",
            ".csv",
            ".jpg",
            ".jpeg",
            ".png",
            ".webp",
            ".mp4",
            ".mov",
            ".m4v",
        }:
            raise ValueError("素材文件类型不受支持")
        self._root.mkdir(parents=True, exist_ok=True)
        key = f"{asset_id}{normalized_suffix}"
        target = self._path_for(key)
        temporary = target.with_suffix(target.suffix + ".tmp")
        temporary.write_bytes(payload)
        os.replace(temporary, target)
        return key

    def delete(self, object_key: str) -> None:
        target = self._path_for(object_key)
        target.unlink(missing_ok=True)

    def _path_for(self, object_key: str) -> Path:
        if "/" in object_key or "\\" in object_key or not object_key:
            raise ValueError("素材对象标识无效")
        target = (self._root / object_key).resolve()
        if target.parent != self._root:
            raise ValueError("素材对象路径越界")
        return target
