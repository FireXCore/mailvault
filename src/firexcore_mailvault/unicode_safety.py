from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

_REPLACEMENT = "\ufffd"


def sanitize_text(value: str, *, replacement: str = _REPLACEMENT) -> str:
    """Return valid Unicode scalar text without mutating the raw source bytes.

    Email and IMAP parsers may expose undecodable octets through Python's
    surrogateescape range (U+DC80..U+DCFF), or malformed data may contain lone
    UTF-16 surrogate code points. Neither can be encoded to UTF-8 or persisted
    by SQLite. This function repairs surrogateescape runs back through UTF-8,
    combines valid surrogate pairs, and replaces irrecoverable lone surrogates.
    """
    if not value or not _contains_surrogate(value):
        return value

    output: list[str] = []
    index = 0
    length = len(value)

    while index < length:
        code = ord(value[index])

        # Python's surrogateescape maps undecodable bytes 0x80..0xFF to
        # U+DC80..U+DCFF. Recover consecutive escaped bytes and decode them.
        if 0xDC80 <= code <= 0xDCFF:
            escaped = bytearray()
            while index < length:
                current = ord(value[index])
                if not 0xDC80 <= current <= 0xDCFF:
                    break
                escaped.append(current - 0xDC00)
                index += 1
            output.append(bytes(escaped).decode("utf-8", errors="replace"))
            continue

        # Combine a valid UTF-16 surrogate pair into a single Unicode scalar.
        if 0xD800 <= code <= 0xDBFF and index + 1 < length:
            low = ord(value[index + 1])
            if 0xDC00 <= low <= 0xDFFF:
                scalar = 0x10000 + ((code - 0xD800) << 10) + (low - 0xDC00)
                output.append(chr(scalar))
                index += 2
                continue

        if 0xD800 <= code <= 0xDFFF:
            output.append(replacement)
        else:
            output.append(value[index])
        index += 1

    return "".join(output)


def sanitize_optional_text(value: str | None) -> str | None:
    return sanitize_text(value) if value is not None else None


def sanitize_json_value(value: Any) -> Any:
    """Recursively sanitize strings used in JSON, logs, and SQLite JSON fields."""
    if isinstance(value, str):
        return sanitize_text(value)
    if isinstance(value, bytes):
        return value.decode("utf-8", errors="replace")
    if isinstance(value, Mapping):
        return {sanitize_text(str(key)): sanitize_json_value(item) for key, item in value.items()}
    if isinstance(value, tuple):
        return tuple(sanitize_json_value(item) for item in value)
    if isinstance(value, list):
        return [sanitize_json_value(item) for item in value]
    if isinstance(value, set | frozenset):
        return [sanitize_json_value(item) for item in sorted(value, key=repr)]
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
        return [sanitize_json_value(item) for item in value]
    return value


def _contains_surrogate(value: str) -> bool:
    return any(0xD800 <= ord(character) <= 0xDFFF for character in value)
