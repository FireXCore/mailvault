from __future__ import annotations

import json
from pathlib import Path

from firexcore_mailvault.atomic import atomic_write_json
from firexcore_mailvault.serialization import safe_json_dumps
from firexcore_mailvault.unicode_safety import sanitize_json_value, sanitize_text


def test_sanitize_text_repairs_surrogateescape_utf8_sequence() -> None:
    escaped = "price-\udce2\udc82\udcac"

    repaired = sanitize_text(escaped)

    assert repaired == "price-€"
    assert repaired.encode("utf-8") == b"price-\xe2\x82\xac"


def test_sanitize_text_combines_valid_surrogate_pair_and_replaces_lone_surrogate() -> None:
    value = "ok-\ud83d\ude80-bad-\ud800"

    repaired = sanitize_text(value)

    assert repaired == "ok-🚀-bad-�"
    repaired.encode("utf-8")


def test_safe_json_dumps_sanitizes_nested_values_and_keys() -> None:
    payload = {"subject\udcff": ["label\udce2\udc82\udcac", {"x": "\ud800"}]}

    encoded = safe_json_dumps(payload, ensure_ascii=False, sort_keys=True)
    decoded = json.loads(encoded)

    assert decoded == {"subject�": ["label€", {"x": "�"}]}


def test_atomic_write_json_accepts_malformed_derived_text(tmp_path: Path) -> None:
    path = tmp_path / "message.json"

    atomic_write_json(path, {"subject": "broken\udcff"})

    assert json.loads(path.read_text(encoding="utf-8")) == {"subject": "broken�"}


def test_sanitize_json_value_preserves_non_text_scalars() -> None:
    assert sanitize_json_value({"count": 3, "ok": True, "none": None}) == {
        "count": 3,
        "ok": True,
        "none": None,
    }
