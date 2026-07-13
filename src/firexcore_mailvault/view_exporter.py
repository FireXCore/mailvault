from __future__ import annotations

import json
import shutil
import sqlite3
from collections import defaultdict
from pathlib import Path
from typing import Any

from firexcore_mailvault.atomic import atomic_write_json
from firexcore_mailvault.filename import safe_path_segment
from firexcore_mailvault.repository import ArchiveRepository


class ViewExporter:
    def __init__(self, repository: ArchiveRepository, archive_root: Path, views_root: Path) -> None:
        self.repository = repository
        self.archive_root = archive_root
        self.views_root = views_root

    def rebuild(self) -> dict[str, int]:
        if self.views_root.exists():
            shutil.rmtree(self.views_root)
        self.views_root.mkdir(parents=True, exist_ok=True)
        counts: dict[str, int] = defaultdict(int)
        query = """
            SELECT
                m.id AS message_id,
                m.archive_id,
                m.provider_thread_namespace,
                m.provider_thread_value,
                m.header_date,
                m.subject_raw,
                m.raw_path,
                o.internal_date,
                o.labels_json,
                mb.name AS mailbox_name,
                p.id AS part_id,
                p.part_path,
                p.role,
                p.filename_original,
                p.filename_safe,
                p.sha256,
                p.blob_path,
                p.detected_mime_type,
                p.size_bytes
            FROM messages m
            LEFT JOIN message_occurrences o ON o.id=(
                SELECT MIN(o2.id) FROM message_occurrences o2 WHERE o2.message_id=m.id
            )
            LEFT JOIN mailbox_generations g ON g.id=o.generation_id
            LEFT JOIN mailboxes mb ON mb.id=g.mailbox_id
            LEFT JOIN message_parts p ON p.message_id=m.id
            WHERE m.raw_path IS NOT NULL
            ORDER BY m.id, p.part_path
        """
        senders = self._senders()
        for row in self.repository.connection.execute(query):
            pointer = self._pointer(row)
            sender = senders.get(int(row["message_id"]), {})
            domain = sender.get("domain") or "unknown-domain"
            address = sender.get("address") or "unknown-sender"
            year = self._year(row)
            filename = self._pointer_filename(row)
            thread = row["provider_thread_value"] or f"message-{row['archive_id']}"

            targets = [
                self.views_root
                / "by-domain"
                / safe_path_segment(str(domain))
                / safe_path_segment(str(address))
                / year
                / filename,
                self.views_root / "by-thread" / safe_path_segment(str(thread)) / filename,
                self.views_root / "by-year" / year / filename,
                self.views_root
                / "by-mailbox"
                / safe_path_segment(str(row["mailbox_name"] or "unknown-mailbox"))
                / filename,
            ]
            for label in self._json_list(row["labels_json"]):
                targets.append(
                    self.views_root / "by-label" / safe_path_segment(str(label)) / filename
                )
            for target in targets:
                atomic_write_json(target, pointer)
                counts[target.parts[-3] if len(target.parts) >= 3 else "views"] += 1
        return dict(counts)

    def _senders(self) -> dict[int, dict[str, Any]]:
        result: dict[int, dict[str, Any]] = {}
        for row in self.repository.connection.execute(
            """
            SELECT message_id, name, address, domain
            FROM message_participants WHERE role='from' ORDER BY message_id, ordinal
            """
        ):
            result.setdefault(
                int(row["message_id"]),
                {"name": row["name"], "address": row["address"], "domain": row["domain"]},
            )
        return result

    def _pointer(self, row: sqlite3.Row) -> dict[str, Any]:
        return {
            "schema_version": "firexcore.mailvault.pointer.v2",
            "message_archive_id": row["archive_id"],
            "thread": {
                "namespace": row["provider_thread_namespace"],
                "value": row["provider_thread_value"],
            },
            "subject": row["subject_raw"],
            "raw_eml_path": row["raw_path"],
            "part": {
                "part_id": row["part_id"],
                "part_path": row["part_path"],
                "role": row["role"],
                "filename_original": row["filename_original"],
                "sha256": row["sha256"],
                "blob_path": row["blob_path"],
                "detected_mime_type": row["detected_mime_type"],
                "size_bytes": row["size_bytes"],
            }
            if row["part_id"] is not None
            else None,
        }

    @staticmethod
    def _year(row: sqlite3.Row) -> str:
        value = row["internal_date"] or row["header_date"] or ""
        return str(value)[:4] if str(value)[:4].isdigit() else "unknown-year"

    @staticmethod
    def _pointer_filename(row: sqlite3.Row) -> str:
        part = f"part-{row['part_id']}" if row["part_id"] is not None else "message"
        name = row["filename_safe"] or part
        return safe_path_segment(f"{row['archive_id']}__{part}__{name}") + ".json"

    @staticmethod
    def _json_list(value: object) -> list[Any]:
        if not isinstance(value, str):
            return []
        try:
            parsed = json.loads(value)
            return parsed if isinstance(parsed, list) else []
        except json.JSONDecodeError:
            return []
