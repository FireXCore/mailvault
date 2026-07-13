from __future__ import annotations

import re
import unicodedata

from firexcore_mailvault.unicode_safety import sanitize_text

_INVALID = re.compile(r'[\\/:*?"<>|\x00-\x1f]')
_RESERVED = {
    "con",
    "prn",
    "aux",
    "nul",
    *(f"com{i}" for i in range(1, 10)),
    *(f"lpt{i}" for i in range(1, 10)),
}


def safe_filename(value: str | None, fallback: str = "unnamed") -> str:
    if not value:
        return fallback
    name = unicodedata.normalize("NFKC", sanitize_text(value))
    name = _INVALID.sub("_", name).strip(" .")
    if not name:
        name = fallback
    stem = name.split(".", 1)[0].casefold()
    if stem in _RESERVED:
        name = f"_{name}"
    if len(name) > 180:
        if "." in name:
            base, extension = name.rsplit(".", 1)
            name = f"{base[:150]}.{extension[:20]}"
        else:
            name = name[:180]
    return name


def safe_path_segment(value: str | None, fallback: str = "unknown") -> str:
    return safe_filename(value, fallback=fallback).replace("@", "_at_")
