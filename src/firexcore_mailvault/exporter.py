from __future__ import annotations

import os
import tempfile
from pathlib import Path

from firexcore_mailvault.repository import ArchiveRepository
from firexcore_mailvault.serialization import row_to_dict, safe_json_dumps

_TABLE_EXPORTS = {
    "accounts": "accounts.jsonl",
    "mailboxes": "mailboxes.jsonl",
    "mailbox_generations": "mailbox_generations.jsonl",
    "messages": "messages.jsonl",
    "message_identities": "message_identities.jsonl",
    "message_occurrences": "message_occurrences.jsonl",
    "message_participants": "message_participants.jsonl",
    "message_bodies": "message_bodies.jsonl",
    "message_parts": "message_parts.jsonl",
    "message_relations": "message_relations.jsonl",
    "blobs": "blobs.jsonl",
    "failures": "failures.jsonl",
    "runs": "runs.jsonl",
}


def export_jsonl(repository: ArchiveRepository, destination: Path) -> list[Path]:
    destination.mkdir(parents=True, exist_ok=True)
    written: list[Path] = []
    for table, filename in _TABLE_EXPORTS.items():
        output = destination / filename
        fd, temp_name = tempfile.mkstemp(prefix=f".{filename}.", suffix=".tmp", dir=destination)
        temp_path = Path(temp_name)
        try:
            with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as handle:
                for row in repository.table_rows(table):
                    handle.write(
                        safe_json_dumps(row_to_dict(row), ensure_ascii=False, sort_keys=True)
                    )
                    handle.write("\n")
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temp_path, output)
            written.append(output)
        finally:
            temp_path.unlink(missing_ok=True)
    return written
