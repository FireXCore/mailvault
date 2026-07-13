from __future__ import annotations

import json
import os
import tempfile
from collections import defaultdict
from pathlib import Path
from typing import Any

from firexcore_mailvault.repository import ArchiveRepository
from firexcore_mailvault.serialization import safe_json_dumps


class ProcurementManifestExporter:
    """Export immutable source anchors for downstream procurement intelligence.

    The exporter performs no classification and creates no commercial facts. It guarantees
    that downstream extractors can cite a message body or MIME part back to its immutable
    source object, participants, thread, date, mailbox occurrence, and content hash.
    """

    def __init__(self, repository: ArchiveRepository) -> None:
        self.repository = repository

    def export(self, destination: Path) -> Path:
        destination.parent.mkdir(parents=True, exist_ok=True)
        participants = self._participants()
        fd, temp_name = tempfile.mkstemp(
            prefix=f".{destination.name}.", suffix=".tmp", dir=destination.parent
        )
        temp_path = Path(temp_name)
        try:
            with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as handle:
                current_message_id: int | None = None
                body_written = False
                for row in self.repository.procurement_rows():
                    message_id = int(row["message_id"])
                    if message_id != current_message_id:
                        current_message_id = message_id
                        body_written = False
                    base = self._base(row, participants.get(message_id, {}))
                    if not body_written:
                        body_text = row["plain_text"] or row["html_visible_text"]
                        if body_text:
                            record = {
                                **base,
                                "artifact": {
                                    "kind": "message_body",
                                    "mime_type": "text/plain",
                                    "text": body_text,
                                },
                                "evidence_anchor": {
                                    "scheme": "mailvault-message-body-v1",
                                    "message_archive_id": row["archive_id"],
                                    "body_variant": "plain"
                                    if row["plain_text"]
                                    else "html_visible_text",
                                },
                            }
                            handle.write(
                                safe_json_dumps(record, ensure_ascii=False, sort_keys=True)
                            )
                            handle.write("\n")
                        body_written = True
                    if row["part_id"] is not None:
                        record = {
                            **base,
                            "artifact": {
                                "kind": "mime_part",
                                "part_id": row["part_id"],
                                "part_path": row["part_path"],
                                "role": row["role"],
                                "filename": row["filename_original"],
                                "declared_mime_type": row["declared_mime_type"],
                                "detected_mime_type": row["detected_mime_type"],
                                "sha256": row["part_sha256"],
                                "storage_path": row["blob_path"],
                                "size_bytes": row["size_bytes"],
                            },
                            "evidence_anchor": {
                                "scheme": "mailvault-mime-part-v1",
                                "message_archive_id": row["archive_id"],
                                "part_path": row["part_path"],
                                "blob_sha256": row["part_sha256"],
                            },
                        }
                        handle.write(safe_json_dumps(record, ensure_ascii=False, sort_keys=True))
                        handle.write("\n")
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temp_path, destination)
        finally:
            temp_path.unlink(missing_ok=True)
        return destination

    def _participants(self) -> dict[int, dict[str, list[dict[str, Any]]]]:
        result: dict[int, dict[str, list[dict[str, Any]]]] = defaultdict(lambda: defaultdict(list))
        for row in self.repository.table_rows("message_participants"):
            result[int(row["message_id"])][str(row["role"])].append(
                {
                    "name": row["name"],
                    "address": row["address"],
                    "domain": row["domain"],
                }
            )
        return {message_id: dict(groups) for message_id, groups in result.items()}

    @staticmethod
    def _base(row: Any, participants: dict[str, list[dict[str, Any]]]) -> dict[str, Any]:
        labels: list[str] = []
        if row["labels_json"]:
            try:
                parsed = json.loads(str(row["labels_json"]))
                labels = parsed if isinstance(parsed, list) else []
            except json.JSONDecodeError:
                labels = []
        return {
            "schema_version": "firexcore.mailvault.procurement-source.v1",
            "message": {
                "archive_id": row["archive_id"],
                "rfc_message_id": row["rfc_message_id"],
                "thread_namespace": row["provider_thread_namespace"],
                "thread_value": row["provider_thread_value"],
                "subject": row["subject_raw"],
                "subject_normalized": row["subject_normalized"],
                "header_date": row["header_date"],
                "internal_date": row["internal_date"],
                "raw_sha256": row["raw_sha256"],
                "raw_path": row["raw_path"],
                "mailbox": row["mailbox_name"],
                "labels": labels,
                "participants": participants,
            },
        }
