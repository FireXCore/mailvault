from __future__ import annotations

import mimetypes
from pathlib import Path

_SIGNATURES: tuple[tuple[bytes, str], ...] = (
    (b"%PDF-", "application/pdf"),
    (b"\x89PNG\r\n\x1a\n", "image/png"),
    (b"\xff\xd8\xff", "image/jpeg"),
    (b"GIF87a", "image/gif"),
    (b"GIF89a", "image/gif"),
    (b"PK\x03\x04", "application/zip"),
    (b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1", "application/x-ole-storage"),
    (b"{\\rtf", "application/rtf"),
    (b"MZ", "application/x-dosexec"),
)


def detect_mime(payload: bytes, filename: str | None, declared: str | None = None) -> str:
    for signature, mime_type in _SIGNATURES:
        if payload.startswith(signature):
            if mime_type == "application/zip" and filename:
                suffix = Path(filename).suffix.casefold()
                office = {
                    ".docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                    ".xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                    ".pptx": "application/vnd.openxmlformats-officedocument.presentationml.presentation",
                }
                return office.get(suffix, mime_type)
            return mime_type
    if filename:
        guessed, _ = mimetypes.guess_type(filename)
        if guessed:
            return guessed
    return declared or "application/octet-stream"
