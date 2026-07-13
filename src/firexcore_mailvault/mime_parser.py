from __future__ import annotations

import hashlib
import re
from collections import defaultdict
from dataclasses import dataclass
from email import policy
from email.message import EmailMessage, Message
from email.parser import BytesParser
from typing import Any

from firexcore_mailvault.archive import BlobStore
from firexcore_mailvault.filename import safe_filename
from firexcore_mailvault.html_text import html_to_visible_text
from firexcore_mailvault.models import ParsedMessage, ParsedPart, PartRole
from firexcore_mailvault.unicode_safety import sanitize_text

_CID_RE = re.compile(r"cid:([^\"'\s)>]+)", re.IGNORECASE)
_SECURITY_MIMES = {
    "application/pkcs7-signature",
    "application/x-pkcs7-signature",
}
_ENCRYPTED_MIMES = {
    "application/pkcs7-mime",
    "application/x-pkcs7-mime",
    "application/pgp-encrypted",
}


@dataclass(slots=True)
class MimeParseResult:
    parsed_message: ParsedMessage
    part_records: list[dict[str, Any]]


def parse_message(raw: bytes, blob_store: BlobStore) -> MimeParseResult:
    root = BytesParser(policy=policy.default).parsebytes(raw)
    if not isinstance(root, EmailMessage):
        root = _coerce_email_message(root)

    referenced_cids = _collect_referenced_cids(root)
    plain_candidates: list[str] = []
    html_candidates: list[str] = []
    charsets: set[str] = set()
    parsed_parts: list[ParsedPart] = []
    records: list[dict[str, Any]] = []

    def visit(part: Message, path: str, parent: str | None) -> None:
        if part.is_multipart() and part.get_content_type().casefold() != "message/rfc822":
            children = list(_iter_children(part))
            for index, child in enumerate(children, start=1):
                child_path = str(index) if path == "0" else f"{path}.{index}"
                visit(child, child_path, None if path == "0" else path)
            return

        declared = part.get_content_type().casefold()
        disposition = part.get_content_disposition()
        raw_filename = part.get_filename()
        filename_original = sanitize_text(raw_filename) if raw_filename else None
        filename_safe = safe_filename(filename_original) if filename_original else None
        content_id = _clean_content_id(part.get("Content-ID"))
        raw_charset = part.get_content_charset()
        charset = sanitize_text(raw_charset) if raw_charset else None
        if charset:
            charsets.add(charset.casefold())
        transfer_encoding = _optional(part.get("Content-Transfer-Encoding"))
        role = _classify_role(
            declared,
            disposition,
            filename_original,
            content_id,
            referenced_cids,
        )
        payload = _payload_bytes(part)
        if role in {PartRole.BODY_PLAIN, PartRole.BODY_HTML}:
            text_value = _decode_text_part(part, payload)
            if text_value:
                if role is PartRole.BODY_PLAIN:
                    plain_candidates.append(text_value)
                else:
                    html_candidates.append(text_value)

        blob_sha: str | None = None
        blob_path: str | None = None
        detected_mime: str | None = declared
        if role not in {PartRole.BODY_PLAIN, PartRole.BODY_HTML} and payload is not None:
            stored = blob_store.store_blob(payload, filename_original, declared)
            blob_sha = stored.sha256
            blob_path = stored.relative_path
            detected_mime = stored.detected_mime_type

        headers = _headers_dict(part)
        defects = [type(defect).__name__ for defect in getattr(part, "defects", [])]
        parsed_part = ParsedPart(
            part_path=path,
            parent_part_path=parent,
            role=role,
            declared_mime_type=declared,
            detected_mime_type=detected_mime,
            content_disposition=disposition,
            content_id=content_id,
            filename_original=filename_original,
            filename_safe=filename_safe,
            charset=charset,
            transfer_encoding=transfer_encoding,
            size_bytes=len(payload) if payload is not None else 0,
            sha256=blob_sha,
            blob_path=blob_path,
            headers=headers,
            defects=defects,
        )
        parsed_parts.append(parsed_part)
        records.append(
            {
                "part_path": parsed_part.part_path,
                "parent_part_path": parsed_part.parent_part_path,
                "role": parsed_part.role.value,
                "declared_mime_type": parsed_part.declared_mime_type,
                "detected_mime_type": parsed_part.detected_mime_type,
                "content_disposition": parsed_part.content_disposition,
                "content_id": parsed_part.content_id,
                "filename_original": parsed_part.filename_original,
                "filename_safe": parsed_part.filename_safe,
                "charset": parsed_part.charset,
                "transfer_encoding": parsed_part.transfer_encoding,
                "size_bytes": parsed_part.size_bytes,
                "sha256": parsed_part.sha256,
                "blob_path": parsed_part.blob_path,
                "headers": parsed_part.headers,
                "defects": parsed_part.defects,
            }
        )

    if root.is_multipart():
        for index, child in enumerate(root.iter_parts(), start=1):
            visit(child, str(index), None)
    else:
        visit(root, "1", None)

    plain = _best_body(plain_candidates)
    html = _best_body(html_candidates)
    parsed = ParsedMessage(
        plain_text=plain,
        html_text=html,
        html_visible_text=html_to_visible_text(html),
        charsets=tuple(sorted(charsets)),
        parts=parsed_parts,
        defects=[type(defect).__name__ for defect in getattr(root, "defects", [])],
    )
    return MimeParseResult(parsed_message=parsed, part_records=records)


def raw_sha256(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def _collect_referenced_cids(root: EmailMessage) -> set[str]:
    result: set[str] = set()
    for part in root.walk():
        if part.is_multipart() or part.get_content_type().casefold() != "text/html":
            continue
        if part.get_content_disposition() == "attachment" or part.get_filename():
            continue
        payload = _payload_bytes(part)
        html = _decode_text_part(part, payload)
        for value in _CID_RE.findall(html or ""):
            result.add(value.strip("<>").casefold())
    return result


def _classify_role(
    declared: str,
    disposition: str | None,
    filename: str | None,
    content_id: str | None,
    referenced_cids: set[str],
) -> PartRole:
    lower_name = filename.casefold() if filename else ""
    if declared in _SECURITY_MIMES or lower_name == "smime.p7s":
        return PartRole.SECURITY_ARTIFACT
    if declared in _ENCRYPTED_MIMES:
        return PartRole.ENCRYPTED_CONTAINER
    if (
        declared in {"application/ms-tnef", "application/vnd.ms-tnef"}
        or lower_name == "winmail.dat"
    ):
        return PartRole.TNEF_CONTAINER
    if declared == "message/rfc822":
        return PartRole.NESTED_MESSAGE
    if declared == "text/plain" and disposition != "attachment" and not filename:
        return PartRole.BODY_PLAIN
    if declared == "text/html" and disposition != "attachment" and not filename:
        return PartRole.BODY_HTML
    if content_id and (disposition == "inline" or content_id.casefold() in referenced_cids):
        return PartRole.INLINE_RESOURCE
    if disposition == "inline" and declared.startswith("image/"):
        return PartRole.INLINE_RESOURCE
    if disposition == "attachment" or filename:
        return PartRole.ATTACHMENT
    return PartRole.UNKNOWN


def _payload_bytes(part: Message) -> bytes | None:
    if part.get_content_type().casefold() == "message/rfc822":
        payload = part.get_payload()
        if isinstance(payload, list) and payload:
            nested = payload[0]
            if isinstance(nested, Message):
                return nested.as_bytes(policy=policy.default)
    decoded = part.get_payload(decode=True)
    if isinstance(decoded, bytes):
        return decoded
    raw_payload = part.get_payload()
    if isinstance(raw_payload, str):
        charset = part.get_content_charset() or "utf-8"
        return raw_payload.encode(charset, errors="replace")
    return None


def _decode_text_part(part: Message, payload: bytes | None) -> str | None:
    if isinstance(part, EmailMessage):
        try:
            content = part.get_content()
            if isinstance(content, str):
                return sanitize_text(content)
        except (LookupError, UnicodeError, AttributeError):
            pass
    if payload is None:
        return None
    candidates = [part.get_content_charset(), "utf-8", "windows-1256", "windows-1252", "latin-1"]
    for charset in candidates:
        if not charset:
            continue
        try:
            return sanitize_text(payload.decode(charset))
        except (LookupError, UnicodeDecodeError):
            continue
    return sanitize_text(payload.decode("utf-8", errors="replace"))


def _headers_dict(part: Message) -> dict[str, list[str]]:
    result: dict[str, list[str]] = defaultdict(list)
    for name, value in part.raw_items():
        result[sanitize_text(name)].append(sanitize_text(str(value)))
    return dict(result)


def _best_body(values: list[str]) -> str | None:
    unique = list(dict.fromkeys(value.strip() for value in values if value.strip()))
    if not unique:
        return None
    return max(unique, key=len)


def _clean_content_id(value: object | None) -> str | None:
    text = _optional(value)
    return text.strip("<>") if text else None


def _optional(value: object | None) -> str | None:
    if value is None:
        return None
    text = sanitize_text(str(value)).strip()
    return text or None


def _iter_children(part: Message) -> list[Message]:
    payload = part.get_payload()
    if isinstance(payload, list):
        return [child for child in payload if isinstance(child, Message)]
    return []


def _coerce_email_message(message: Message) -> EmailMessage:
    parsed = BytesParser(policy=policy.default).parsebytes(message.as_bytes(policy=policy.default))
    if not isinstance(parsed, EmailMessage):
        raise TypeError("Unable to parse message as EmailMessage")
    return parsed
