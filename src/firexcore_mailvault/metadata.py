from __future__ import annotations

from collections import defaultdict
from datetime import datetime
from email import policy
from email.header import decode_header
from email.message import Message
from email.parser import BytesHeaderParser
from email.utils import parsedate_to_datetime

from firexcore_mailvault.models import ParsedHeaders
from firexcore_mailvault.participants import parse_addresses
from firexcore_mailvault.subject import normalize_subject
from firexcore_mailvault.unicode_safety import sanitize_text


def _safe_date(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        return parsedate_to_datetime(value)
    except (TypeError, ValueError, OverflowError):
        return None


def _decode_header_value(value: object) -> str:
    """Decode RFC 2047 words without invoking headerregistry address parsing.

    Real-world archives contain malformed group syntax and legacy address headers
    that can crash Python's structured headerregistry parser.  MailVault treats
    header bytes as evidence and performs a tolerant, string-based decode here.
    """
    raw = sanitize_text(str(value))
    decoded: list[str] = []
    try:
        fragments = decode_header(raw)
    except (LookupError, UnicodeError, ValueError):
        return raw

    for fragment, charset in fragments:
        if isinstance(fragment, bytes):
            candidates = [charset, "utf-8", "latin-1"]
            text: str | None = None
            for candidate in candidates:
                if not candidate:
                    continue
                try:
                    text = fragment.decode(candidate, errors="strict")
                    break
                except (LookupError, UnicodeError):
                    continue
            if text is None:
                text = fragment.decode("utf-8", errors="replace")
            decoded.append(text)
        else:
            decoded.append(fragment)
    return sanitize_text("".join(decoded))


def _header_values(message: Message, name: str) -> list[str]:
    values = message.get_all(name, [])
    return [_decode_header_value(value) for value in values]


def parse_header_bytes(header_bytes: bytes) -> ParsedHeaders:
    message = BytesHeaderParser(policy=policy.compat32).parsebytes(header_bytes)
    all_headers: dict[str, list[str]] = defaultdict(list)
    for name, value in message.raw_items():
        all_headers[sanitize_text(name)].append(_decode_header_value(value))

    subject = _decode_header_value(message.get("Subject", ""))
    references: list[str] = []
    for raw in _header_values(message, "References"):
        references.extend(token for token in raw.split() if token)

    return ParsedHeaders(
        rfc_message_id=_optional_header(message.get("Message-ID")),
        in_reply_to=_optional_header(message.get("In-Reply-To")),
        references=tuple(dict.fromkeys(references)),
        subject_raw=subject,
        subject_normalized=normalize_subject(subject),
        from_values=parse_addresses(_header_values(message, "From")),
        sender_values=parse_addresses(_header_values(message, "Sender")),
        reply_to_values=parse_addresses(_header_values(message, "Reply-To")),
        to_values=parse_addresses(_header_values(message, "To")),
        cc_values=parse_addresses(_header_values(message, "Cc")),
        bcc_values=parse_addresses(_header_values(message, "Bcc")),
        return_path=_optional_header(message.get("Return-Path")),
        delivered_to=tuple(_header_values(message, "Delivered-To")),
        x_original_to=tuple(_header_values(message, "X-Original-To")),
        list_id=_optional_header(message.get("List-ID")),
        header_date=_safe_date(_optional_header(message.get("Date"))),
        content_type=_optional_header(message.get("Content-Type")),
        authentication_results=tuple(_header_values(message, "Authentication-Results")),
        received_headers=tuple(_header_values(message, "Received")),
        all_headers=dict(all_headers),
    )


def _optional_header(value: object | None) -> str | None:
    if value is None:
        return None
    text = _decode_header_value(value).strip()
    return text or None
