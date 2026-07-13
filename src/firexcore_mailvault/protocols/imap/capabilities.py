from __future__ import annotations

import re
from collections.abc import Iterable

from firexcore_mailvault.models import ServerCapabilities

_LIMIT_RE = re.compile(r"^(MESSAGE|SAVE)LIMIT=(\d+)$", re.IGNORECASE)


def parse_capabilities(values: Iterable[bytes | str]) -> ServerCapabilities:
    raw = tuple(sorted({_text(value).upper() for value in values if _text(value)}))
    folded = {value.casefold() for value in raw}
    message_limit: int | None = None
    save_limit: int | None = None
    for value in raw:
        match = _LIMIT_RE.match(value)
        if not match:
            continue
        limit = int(match.group(2))
        if match.group(1).casefold() == "message":
            message_limit = limit
        else:
            save_limit = limit
    return ServerCapabilities(
        raw=raw,
        imap4rev2="imap4rev2" in folded,
        gmail_extensions="x-gm-ext-1" in folded,
        object_id="objectid" in folded,
        condstore="condstore" in folded,
        qresync="qresync" in folded,
        special_use="special-use" in folded or "imap4rev2" in folded,
        uidplus="uidplus" in folded or "imap4rev2" in folded,
        idle="idle" in folded or "imap4rev2" in folded,
        literal_plus="literal+" in folded or "imap4rev2" in folded,
        uid_only="uidonly" in folded,
        message_limit=message_limit,
        save_limit=save_limit,
    )


def effective_batch_size(configured: int, capabilities: ServerCapabilities) -> int:
    if capabilities.message_limit is None:
        return configured
    return max(1, min(configured, capabilities.message_limit))


def _text(value: bytes | str) -> str:
    if isinstance(value, bytes):
        return value.decode("ascii", errors="ignore").strip()
    return str(value).strip()
