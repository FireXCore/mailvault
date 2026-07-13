from __future__ import annotations

import logging
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from firexcore_mailvault.serialization import safe_json_dumps
from firexcore_mailvault.unicode_safety import sanitize_text


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, Any] = {
            "timestamp": datetime.now(UTC).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": sanitize_text(record.getMessage()),
        }
        if record.exc_info:
            payload["exception"] = sanitize_text(self.formatException(record.exc_info))
        return safe_json_dumps(payload, ensure_ascii=False)


def configure_logging(log_path: Path, level: str = "INFO") -> None:
    root = logging.getLogger()
    root.setLevel(level.upper())
    root.handlers.clear()

    console = logging.StreamHandler()
    console.setFormatter(logging.Formatter("%(levelname)s %(message)s"))
    root.addHandler(console)

    log_path.parent.mkdir(parents=True, exist_ok=True)
    file_handler = logging.FileHandler(log_path, encoding="utf-8", errors="backslashreplace")
    file_handler.setFormatter(JsonFormatter())
    root.addHandler(file_handler)
