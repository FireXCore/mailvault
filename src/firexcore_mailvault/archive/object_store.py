from __future__ import annotations

import hashlib
from dataclasses import dataclass
from pathlib import Path

from firexcore_mailvault.atomic import atomic_write_bytes
from firexcore_mailvault.errors import ArchiveConflictError
from firexcore_mailvault.mime_detect import detect_mime


@dataclass(frozen=True, slots=True)
class StoredObject:
    sha256: str
    size_bytes: int
    relative_path: str
    already_existed: bool
    detected_mime_type: str | None = None


class ContentAddressedStore:
    def __init__(self, root: Path, archive_root: Path) -> None:
        self.root = root
        self.archive_root = archive_root
        self.root.mkdir(parents=True, exist_ok=True)

    def path_for(self, digest: str) -> Path:
        return self.root / digest[:2] / digest[2:4] / digest

    def store(self, payload: bytes) -> StoredObject:
        digest = hashlib.sha256(payload).hexdigest()
        path = self.path_for(digest)
        existed = path.exists()
        if existed:
            if path.stat().st_size != len(payload):
                raise ArchiveConflictError(
                    f"Existing object {digest} has a different size; archive may be corrupted."
                )
        else:
            atomic_write_bytes(path, payload)
        return StoredObject(
            sha256=digest,
            size_bytes=len(payload),
            relative_path=path.relative_to(self.archive_root).as_posix(),
            already_existed=existed,
        )


class BlobStore(ContentAddressedStore):
    def store_blob(
        self,
        payload: bytes,
        filename: str | None,
        declared_mime_type: str | None,
    ) -> StoredObject:
        stored = self.store(payload)
        return StoredObject(
            sha256=stored.sha256,
            size_bytes=stored.size_bytes,
            relative_path=stored.relative_path,
            already_existed=stored.already_existed,
            detected_mime_type=detect_mime(payload, filename, declared_mime_type),
        )
