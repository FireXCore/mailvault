from __future__ import annotations

import re
import unicodedata

from firexcore_mailvault.unicode_safety import sanitize_text

_PREFIX_RE = re.compile(
    r"^(?:(?:re|fw|fwd|aw|wg|sv|答复|回复|转发|پاسخ|ارسال مجدد)\s*[:\uFF1A]\s*)+",
    re.IGNORECASE,
)
_WHITESPACE_RE = re.compile(r"\s+")


def normalize_subject(subject: str | None) -> str:
    if not subject:
        return ""
    value = unicodedata.normalize("NFKC", sanitize_text(subject)).strip()
    previous = None
    while previous != value:
        previous = value
        value = _PREFIX_RE.sub("", value).strip()
    return _WHITESPACE_RE.sub(" ", value).casefold()
