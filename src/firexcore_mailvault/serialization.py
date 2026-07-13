from __future__ import annotations

import json
import sqlite3
from typing import Any, cast

from firexcore_mailvault.unicode_safety import sanitize_json_value


def row_to_dict(row: sqlite3.Row) -> dict[str, Any]:
    output: dict[str, Any] = {}
    for key in row.keys():  # noqa: SIM118 - sqlite3.Row iteration yields values
        value = row[key]
        if key.endswith("_json") and isinstance(value, str):
            try:
                output[key.removesuffix("_json")] = json.loads(value)
            except json.JSONDecodeError:
                output[key] = value
        else:
            output[key] = value
    return cast(dict[str, Any], sanitize_json_value(output))


def safe_json_dumps(
    value: Any,
    *,
    ensure_ascii: bool = False,
    indent: int | None = None,
    sort_keys: bool = False,
) -> str:
    return json.dumps(
        sanitize_json_value(value),
        ensure_ascii=ensure_ascii,
        indent=indent,
        sort_keys=sort_keys,
    )
