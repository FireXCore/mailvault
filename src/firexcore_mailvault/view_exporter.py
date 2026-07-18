from __future__ import annotations

import hashlib
import json
import os
import shutil
import sqlite3
import time
from collections import defaultdict
from collections.abc import Callable, Iterator
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from firexcore_mailvault.atomic import atomic_write_json
from firexcore_mailvault.filename import safe_path_segment
from firexcore_mailvault.repository import ArchiveRepository
from firexcore_mailvault.serialization import safe_json_dumps

_VIEW_SEGMENT_MAX_LENGTH = 64
_POINTER_NAME_HASH_LENGTH = 16
_VIEW_LAYOUT_VERSION = "firexcore.mailvault.views.v3"
_BUILD_STATE_SCHEMA_VERSION = 1
_CHECKPOINT_ROW_INTERVAL = 250
_CHECKPOINT_SECONDS = 2.0
_PROGRESS_ROW_INTERVAL = 25

ProgressCallback = Callable[[str, dict[str, object]], None]


@dataclass(frozen=True, slots=True)
class ViewBuildResult:
    counts: dict[str, int]
    resumed: bool
    up_to_date: bool
    rows_processed: int
    total_rows: int
    pointers_written: int
    total_pointers: int
    source_fingerprint: str


@dataclass(frozen=True, slots=True)
class _ViewPlan:
    source_fingerprint: str
    total_rows: int
    total_pointers: int


@dataclass(frozen=True, slots=True)
class _Cursor:
    message_id: int
    part_path: str
    part_id: int

    @classmethod
    def from_row(cls, row: sqlite3.Row) -> _Cursor:
        return cls(
            message_id=int(row["message_id"]),
            part_path=str(row["part_path"] or ""),
            part_id=int(row["part_id"] or 0),
        )

    @classmethod
    def from_json(cls, value: object) -> _Cursor | None:
        if value is None:
            return None
        if not isinstance(value, dict):
            raise ValueError("Invalid view checkpoint cursor.")
        return cls(
            message_id=int(value["message_id"]),
            part_path=str(value["part_path"]),
            part_id=int(value["part_id"]),
        )

    def to_json(self) -> dict[str, object]:
        return {
            "message_id": self.message_id,
            "part_path": self.part_path,
            "part_id": self.part_id,
        }


class ViewExporter:
    def __init__(
        self,
        repository: ArchiveRepository,
        archive_root: Path,
        views_root: Path,
    ) -> None:
        self.repository = repository
        self.archive_root = archive_root
        self.views_root = views_root
        self.state_root = archive_root / "state"
        self.staging_root = self.state_root / "views-rebuild-staging-v3"
        self.checkpoint_path = self.state_root / "views-rebuild-v1.json"
        self.previous_root = self.state_root / "views-previous"
        self.marker_name = "_mailvault_views.json"

    def rebuild(
        self,
        *,
        restart: bool = False,
        progress: ProgressCallback | None = None,
    ) -> ViewBuildResult:
        self.state_root.mkdir(parents=True, exist_ok=True)
        self._recover_interrupted_publish()

        connection = self.repository.connection
        owns_transaction = not connection.in_transaction
        if owns_transaction:
            connection.execute("BEGIN")

        try:
            senders = self._senders()
            plan = self._plan(senders, progress)

            if not restart:
                current = self._current_result(plan)
                if current is not None:
                    self._cleanup_completed_build()
                    self._emit(
                        progress,
                        "completed",
                        self._result_payload(current),
                    )
                    return current

            state, resumed = self._prepare_state(plan, restart=restart)
            cursor = _Cursor.from_json(state.get("cursor"))
            processed_rows = int(state["processed_rows"])
            pointers_written = int(state["pointers_written"])
            counts = defaultdict(
                int,
                {str(key): int(value) for key, value in self._state_counts(state).items()},
            )

            self._emit(
                progress,
                "build_started",
                {
                    "resumed": resumed,
                    "processed_rows": processed_rows,
                    "total_rows": plan.total_rows,
                    "pointers_written": pointers_written,
                    "total_pointers": plan.total_pointers,
                },
            )

            last_checkpoint_at = time.monotonic()
            rows_since_checkpoint = 0
            rows_since_progress = 0

            try:
                for row in self._rows_after(cursor):
                    pointer = self._pointer(row)
                    sender = senders.get(int(row["message_id"]), {})
                    targets = self._targets(row, sender, self.staging_root)

                    for view_name, target in targets:
                        atomic_write_json(target, pointer)
                        counts[view_name] += 1
                        pointers_written += 1

                    cursor = _Cursor.from_row(row)
                    processed_rows += 1
                    rows_since_checkpoint += 1
                    rows_since_progress += 1

                    now = time.monotonic()
                    if (
                        rows_since_checkpoint >= _CHECKPOINT_ROW_INTERVAL
                        or now - last_checkpoint_at >= _CHECKPOINT_SECONDS
                    ):
                        self._write_checkpoint(
                            state,
                            cursor=cursor,
                            processed_rows=processed_rows,
                            pointers_written=pointers_written,
                            counts=counts,
                            phase="building",
                        )
                        rows_since_checkpoint = 0
                        last_checkpoint_at = now

                    if (
                        rows_since_progress >= _PROGRESS_ROW_INTERVAL
                        or processed_rows == plan.total_rows
                    ):
                        self._emit(
                            progress,
                            "advanced",
                            {
                                "processed_rows": processed_rows,
                                "total_rows": plan.total_rows,
                                "pointers_written": pointers_written,
                                "total_pointers": plan.total_pointers,
                            },
                        )
                        rows_since_progress = 0
            except BaseException:
                self._write_checkpoint(
                    state,
                    cursor=cursor,
                    processed_rows=processed_rows,
                    pointers_written=pointers_written,
                    counts=counts,
                    phase="building",
                )
                self._emit(
                    progress,
                    "interrupted",
                    {
                        "processed_rows": processed_rows,
                        "total_rows": plan.total_rows,
                        "pointers_written": pointers_written,
                        "total_pointers": plan.total_pointers,
                    },
                )
                raise

            if processed_rows != plan.total_rows:
                raise RuntimeError(
                    "View build source row count changed during a protected snapshot."
                )
            if pointers_written != plan.total_pointers:
                raise RuntimeError("View build pointer count does not match the planned snapshot.")

            self._write_checkpoint(
                state,
                cursor=cursor,
                processed_rows=processed_rows,
                pointers_written=pointers_written,
                counts=counts,
                phase="publishing",
            )
            marker = self._marker_payload(
                plan,
                counts=dict(counts),
                completed_at=self._now(),
            )
            atomic_write_json(self.staging_root / self.marker_name, marker)
            self._emit(
                progress,
                "publishing",
                {
                    "processed_rows": processed_rows,
                    "total_rows": plan.total_rows,
                    "pointers_written": pointers_written,
                    "total_pointers": plan.total_pointers,
                },
            )
            self._publish()
            self.checkpoint_path.unlink(missing_ok=True)

            result = ViewBuildResult(
                counts=dict(counts),
                resumed=resumed,
                up_to_date=False,
                rows_processed=processed_rows,
                total_rows=plan.total_rows,
                pointers_written=pointers_written,
                total_pointers=plan.total_pointers,
                source_fingerprint=plan.source_fingerprint,
            )
            self._emit(progress, "completed", self._result_payload(result))
            return result
        finally:
            if owns_transaction and connection.in_transaction:
                connection.rollback()

    def _plan(
        self,
        senders: dict[int, dict[str, Any]],
        progress: ProgressCallback | None,
    ) -> _ViewPlan:
        digest = hashlib.sha256()
        digest.update((_VIEW_LAYOUT_VERSION + "\n").encode())
        total_rows = 0
        total_pointers = 0

        self._emit(progress, "planning", {"rows_scanned": 0})
        for row in self._rows_after(None):
            sender = senders.get(int(row["message_id"]), {})
            labels = self._json_list(row["labels_json"])
            total_rows += 1
            total_pointers += 4 + len(labels)
            digest.update(
                safe_json_dumps(
                    [
                        row[key]
                        for key in (
                            "message_id",
                            "archive_id",
                            "provider_thread_namespace",
                            "provider_thread_value",
                            "header_date",
                            "subject_raw",
                            "raw_path",
                            "internal_date",
                            "labels_json",
                            "mailbox_name",
                            "part_id",
                            "part_path",
                            "role",
                            "filename_original",
                            "filename_safe",
                            "sha256",
                            "blob_path",
                            "detected_mime_type",
                            "size_bytes",
                        )
                    ]
                    + [sender.get("address"), sender.get("domain")],
                    ensure_ascii=True,
                ).encode("utf-8")
            )
            digest.update(b"\n")
            if total_rows % 1000 == 0:
                self._emit(progress, "planning", {"rows_scanned": total_rows})

        plan = _ViewPlan(
            source_fingerprint=digest.hexdigest(),
            total_rows=total_rows,
            total_pointers=total_pointers,
        )
        self._emit(
            progress,
            "planned",
            {
                "total_rows": plan.total_rows,
                "total_pointers": plan.total_pointers,
                "source_fingerprint": plan.source_fingerprint,
            },
        )
        return plan

    def _prepare_state(
        self,
        plan: _ViewPlan,
        *,
        restart: bool,
    ) -> tuple[dict[str, Any], bool]:
        if restart:
            self._discard_incomplete_build()

        state = self._load_checkpoint()
        if state is not None and self.staging_root.is_dir() and self._state_matches(state, plan):
            return state, int(state["processed_rows"]) > 0

        self._discard_incomplete_build()
        self.staging_root.mkdir(parents=True, exist_ok=True)
        now = self._now()
        state = {
            "schema_version": _BUILD_STATE_SCHEMA_VERSION,
            "layout_version": _VIEW_LAYOUT_VERSION,
            "source_fingerprint": plan.source_fingerprint,
            "total_rows": plan.total_rows,
            "total_pointers": plan.total_pointers,
            "processed_rows": 0,
            "pointers_written": 0,
            "counts": {},
            "cursor": None,
            "phase": "building",
            "started_at": now,
            "updated_at": now,
        }
        atomic_write_json(self.checkpoint_path, state)
        return state, False

    def _write_checkpoint(
        self,
        state: dict[str, Any],
        *,
        cursor: _Cursor | None,
        processed_rows: int,
        pointers_written: int,
        counts: dict[str, int],
        phase: str,
    ) -> None:
        state.update(
            {
                "processed_rows": processed_rows,
                "pointers_written": pointers_written,
                "counts": dict(counts),
                "cursor": cursor.to_json() if cursor is not None else None,
                "phase": phase,
                "updated_at": self._now(),
            }
        )
        atomic_write_json(self.checkpoint_path, state)

    def _current_result(self, plan: _ViewPlan) -> ViewBuildResult | None:
        marker_path = self.views_root / self.marker_name
        if not marker_path.is_file():
            return None
        try:
            marker = json.loads(marker_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return None
        if not isinstance(marker, dict):
            return None
        if marker.get("layout_version") != _VIEW_LAYOUT_VERSION:
            return None
        if marker.get("source_fingerprint") != plan.source_fingerprint:
            return None
        if int(marker.get("total_rows", -1)) != plan.total_rows:
            return None
        if int(marker.get("total_pointers", -1)) != plan.total_pointers:
            return None

        counts_value = marker.get("counts")
        if not isinstance(counts_value, dict):
            return None
        counts = {str(key): int(value) for key, value in counts_value.items()}
        return ViewBuildResult(
            counts=counts,
            resumed=False,
            up_to_date=True,
            rows_processed=plan.total_rows,
            total_rows=plan.total_rows,
            pointers_written=plan.total_pointers,
            total_pointers=plan.total_pointers,
            source_fingerprint=plan.source_fingerprint,
        )

    def _state_matches(self, state: dict[str, Any], plan: _ViewPlan) -> bool:
        try:
            if int(state["schema_version"]) != _BUILD_STATE_SCHEMA_VERSION:
                return False
            if state["layout_version"] != _VIEW_LAYOUT_VERSION:
                return False
            if state["source_fingerprint"] != plan.source_fingerprint:
                return False
            if int(state["total_rows"]) != plan.total_rows:
                return False
            if int(state["total_pointers"]) != plan.total_pointers:
                return False
            processed = int(state["processed_rows"])
            pointers = int(state["pointers_written"])
            if not 0 <= processed <= plan.total_rows:
                return False
            if not 0 <= pointers <= plan.total_pointers:
                return False
            cursor = _Cursor.from_json(state.get("cursor"))
            if (processed == 0) != (cursor is None):
                return False
            counts = self._state_counts(state)
            if sum(counts.values()) != pointers:
                return False
            if set(counts) - {
                "by-domain",
                "by-label",
                "by-mailbox",
                "by-thread",
                "by-year",
            }:
                return False
        except (KeyError, TypeError, ValueError):
            return False
        return True

    @staticmethod
    def _state_counts(state: dict[str, Any]) -> dict[str, int]:
        value = state.get("counts")
        if not isinstance(value, dict):
            raise ValueError("Invalid view checkpoint counts.")
        return {str(key): int(count) for key, count in value.items()}

    def _load_checkpoint(self) -> dict[str, Any] | None:
        if not self.checkpoint_path.is_file():
            return None
        try:
            value = json.loads(self.checkpoint_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return None
        return value if isinstance(value, dict) else None

    def _rows_after(self, cursor: _Cursor | None) -> Iterator[sqlite3.Row]:
        where = ""
        parameters: tuple[object, ...] = ()
        if cursor is not None:
            where = """
                AND (
                    m.id > ?
                    OR (m.id = ? AND COALESCE(p.part_path, '') > ?)
                    OR (
                        m.id = ?
                        AND COALESCE(p.part_path, '') = ?
                        AND COALESCE(p.id, 0) > ?
                    )
                )
            """
            parameters = (
                cursor.message_id,
                cursor.message_id,
                cursor.part_path,
                cursor.message_id,
                cursor.part_path,
                cursor.part_id,
            )

        query = (
            """
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
            """
            + where
            + """
            ORDER BY m.id, COALESCE(p.part_path, ''), COALESCE(p.id, 0)
            """
        )
        yield from self.repository.connection.execute(query, parameters)

    def _targets(
        self,
        row: sqlite3.Row,
        sender: dict[str, Any],
        root: Path,
    ) -> list[tuple[str, Path]]:
        domain = sender.get("domain") or "unknown-domain"
        address = sender.get("address") or "unknown-sender"
        year = self._year(row)
        filename = self._pointer_filename(row)
        thread = row["provider_thread_value"] or f"message-{row['archive_id']}"

        targets = [
            (
                "by-domain",
                root
                / "by-domain"
                / self._view_segment(str(domain))
                / self._view_segment(str(address))
                / year
                / filename,
            ),
            (
                "by-thread",
                root / "by-thread" / self._view_segment(str(thread)) / filename,
            ),
            ("by-year", root / "by-year" / year / filename),
            (
                "by-mailbox",
                root
                / "by-mailbox"
                / self._view_segment(str(row["mailbox_name"] or "unknown-mailbox"))
                / filename,
            ),
        ]
        for label in self._json_list(row["labels_json"]):
            targets.append(
                (
                    "by-label",
                    root / "by-label" / self._view_segment(str(label)) / filename,
                )
            )
        return targets

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

    def _publish(self) -> None:
        if self.previous_root.exists():
            shutil.rmtree(self.previous_root)

        had_previous = self.views_root.exists()
        if had_previous:
            os.replace(self.views_root, self.previous_root)

        try:
            os.replace(self.staging_root, self.views_root)
        except BaseException:
            if self.views_root.exists():
                shutil.rmtree(self.views_root)
            if had_previous and self.previous_root.exists():
                os.replace(self.previous_root, self.views_root)
            raise
        else:
            if self.previous_root.exists():
                shutil.rmtree(self.previous_root)

    def _recover_interrupted_publish(self) -> None:
        if not self.previous_root.exists():
            return

        marker = self.views_root / self.marker_name
        if marker.is_file():
            shutil.rmtree(self.previous_root)
            return

        if self.views_root.exists() and any(self.views_root.iterdir()):
            return

        if self.views_root.exists():
            shutil.rmtree(self.views_root)
        os.replace(self.previous_root, self.views_root)

    def _cleanup_completed_build(self) -> None:
        self.checkpoint_path.unlink(missing_ok=True)
        if self.staging_root.exists():
            shutil.rmtree(self.staging_root)
        if self.previous_root.exists():
            shutil.rmtree(self.previous_root)

    def _discard_incomplete_build(self) -> None:
        self.checkpoint_path.unlink(missing_ok=True)
        if self.staging_root.exists():
            shutil.rmtree(self.staging_root)

    def _marker_payload(
        self,
        plan: _ViewPlan,
        *,
        counts: dict[str, int],
        completed_at: str,
    ) -> dict[str, object]:
        return {
            "schema_version": 1,
            "layout_version": _VIEW_LAYOUT_VERSION,
            "source_fingerprint": plan.source_fingerprint,
            "total_rows": plan.total_rows,
            "total_pointers": plan.total_pointers,
            "counts": counts,
            "completed_at": completed_at,
        }

    @staticmethod
    def _result_payload(result: ViewBuildResult) -> dict[str, object]:
        return {
            "resumed": result.resumed,
            "up_to_date": result.up_to_date,
            "processed_rows": result.rows_processed,
            "total_rows": result.total_rows,
            "pointers_written": result.pointers_written,
            "total_pointers": result.total_pointers,
        }

    @staticmethod
    def _emit(
        progress: ProgressCallback | None,
        event: str,
        payload: dict[str, object],
    ) -> None:
        if progress is not None:
            progress(event, payload)

    @staticmethod
    def _now() -> str:
        return datetime.now(UTC).isoformat()

    @staticmethod
    def _year(row: sqlite3.Row) -> str:
        value = row["internal_date"] or row["header_date"] or ""
        return str(value)[:4] if str(value)[:4].isdigit() else "unknown-year"

    @staticmethod
    def _pointer_filename(row: sqlite3.Row) -> str:
        part = f"part-{row['part_id']}" if row["part_id"] is not None else "message"
        identity = "\x1f".join(
            str(value or "")
            for value in (
                row["archive_id"],
                part,
                row["part_path"],
                row["filename_safe"],
                row["sha256"],
            )
        )
        digest = hashlib.sha256(identity.encode("utf-8", errors="surrogatepass")).hexdigest()[
            :_POINTER_NAME_HASH_LENGTH
        ]
        archive_id = ViewExporter._view_segment(str(row["archive_id"] or "message"))
        return f"{archive_id}__{part}__{digest}.json"

    @staticmethod
    def _view_segment(value: str) -> str:
        segment = safe_path_segment(value)
        if len(segment) <= _VIEW_SEGMENT_MAX_LENGTH:
            return segment

        digest = hashlib.sha256(value.encode("utf-8", errors="surrogatepass")).hexdigest()[
            :_POINTER_NAME_HASH_LENGTH
        ]
        prefix_length = _VIEW_SEGMENT_MAX_LENGTH - len(digest) - 2
        return f"{segment[:prefix_length]}__{digest}"

    @staticmethod
    def _json_list(value: object) -> list[Any]:
        if not isinstance(value, str):
            return []
        try:
            parsed = json.loads(value)
            return parsed if isinstance(parsed, list) else []
        except json.JSONDecodeError:
            return []
