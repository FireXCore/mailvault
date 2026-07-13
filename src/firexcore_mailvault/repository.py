from __future__ import annotations

import json
import sqlite3
from collections.abc import Iterable, Iterator, Sequence
from contextlib import contextmanager
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any, cast
from uuid import uuid4

from firexcore_mailvault.config import MailVaultConfig
from firexcore_mailvault.models import (
    MailboxInfo,
    MetadataRecord,
    ParsedHeaders,
    ParsedMessage,
    ProviderKind,
    SelectedMailbox,
    ServerCapabilities,
)
from firexcore_mailvault.serialization import safe_json_dumps
from firexcore_mailvault.unicode_safety import sanitize_optional_text, sanitize_text

_SCHEMA_VERSION = 3

_SCHEMA = r"""
CREATE TABLE IF NOT EXISTS schema_meta (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS accounts (
    id INTEGER PRIMARY KEY,
    archive_id TEXT NOT NULL UNIQUE,
    email TEXT NOT NULL,
    host TEXT NOT NULL,
    port INTEGER NOT NULL,
    provider_kind TEXT NOT NULL,
    tls_mode TEXT NOT NULL,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    UNIQUE(email, host, port)
);

CREATE TABLE IF NOT EXISTS server_snapshots (
    id INTEGER PRIMARY KEY,
    account_id INTEGER NOT NULL REFERENCES accounts(id) ON DELETE CASCADE,
    capabilities_json TEXT NOT NULL,
    observed_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS mailboxes (
    id INTEGER PRIMARY KEY,
    account_id INTEGER NOT NULL REFERENCES accounts(id) ON DELETE CASCADE,
    name TEXT NOT NULL,
    delimiter TEXT,
    flags_json TEXT NOT NULL DEFAULT '[]',
    mailbox_object_id TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    UNIQUE(account_id, name)
);

CREATE TABLE IF NOT EXISTS mailbox_generations (
    id INTEGER PRIMARY KEY,
    mailbox_id INTEGER NOT NULL REFERENCES mailboxes(id) ON DELETE CASCADE,
    uidvalidity INTEGER NOT NULL,
    highest_uid INTEGER NOT NULL DEFAULT 0,
    highest_modseq INTEGER,
    last_scan_at TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    UNIQUE(mailbox_id, uidvalidity)
);

CREATE TABLE IF NOT EXISTS scan_checkpoints (
    id INTEGER PRIMARY KEY,
    generation_id INTEGER NOT NULL REFERENCES mailbox_generations(id) ON DELETE CASCADE,
    selection_key TEXT NOT NULL,
    highest_uid INTEGER NOT NULL DEFAULT 0,
    highest_modseq INTEGER,
    last_scan_at TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    UNIQUE(generation_id, selection_key)
);

CREATE INDEX IF NOT EXISTS idx_scan_checkpoints_generation
    ON scan_checkpoints(generation_id);

CREATE TABLE IF NOT EXISTS runs (
    id INTEGER PRIMARY KEY,
    account_id INTEGER NOT NULL REFERENCES accounts(id) ON DELETE CASCADE,
    started_at TEXT NOT NULL,
    finished_at TEXT,
    status TEXT NOT NULL,
    scope TEXT NOT NULL,
    query_text TEXT,
    mailboxes_scanned INTEGER NOT NULL DEFAULT 0,
    metadata_scanned INTEGER NOT NULL DEFAULT 0,
    raw_archived INTEGER NOT NULL DEFAULT 0,
    bytes_downloaded INTEGER NOT NULL DEFAULT 0,
    errors INTEGER NOT NULL DEFAULT 0,
    stop_reason TEXT
);

CREATE TABLE IF NOT EXISTS messages (
    id INTEGER PRIMARY KEY,
    archive_id TEXT NOT NULL UNIQUE,
    account_id INTEGER NOT NULL REFERENCES accounts(id) ON DELETE CASCADE,
    provider_thread_namespace TEXT,
    provider_thread_value TEXT,
    rfc_message_id TEXT,
    in_reply_to TEXT,
    references_json TEXT NOT NULL DEFAULT '[]',
    subject_raw TEXT NOT NULL DEFAULT '',
    subject_normalized TEXT NOT NULL DEFAULT '',
    return_path TEXT,
    delivered_to_json TEXT NOT NULL DEFAULT '[]',
    x_original_to_json TEXT NOT NULL DEFAULT '[]',
    list_id TEXT,
    header_date TEXT,
    content_type_header TEXT,
    authentication_results_json TEXT NOT NULL DEFAULT '[]',
    received_headers_json TEXT NOT NULL DEFAULT '[]',
    headers_json TEXT NOT NULL DEFAULT '{}',
    raw_path TEXT,
    raw_sha256 TEXT,
    raw_size_bytes INTEGER,
    raw_archived_at TEXT,
    mime_parsed_at TEXT,
    parse_defects_json TEXT NOT NULL DEFAULT '[]',
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_messages_account_raw ON messages(account_id, raw_sha256);
CREATE INDEX IF NOT EXISTS idx_messages_rfc_id ON messages(account_id, rfc_message_id);
CREATE INDEX IF NOT EXISTS idx_messages_thread ON messages(account_id, provider_thread_namespace, provider_thread_value);

CREATE TABLE IF NOT EXISTS message_identities (
    id INTEGER PRIMARY KEY,
    account_id INTEGER NOT NULL REFERENCES accounts(id) ON DELETE CASCADE,
    message_id INTEGER NOT NULL REFERENCES messages(id) ON DELETE CASCADE,
    namespace TEXT NOT NULL,
    value TEXT NOT NULL,
    created_at TEXT NOT NULL,
    UNIQUE(account_id, namespace, value)
);

CREATE INDEX IF NOT EXISTS idx_identities_message ON message_identities(message_id);

CREATE TABLE IF NOT EXISTS message_occurrences (
    id INTEGER PRIMARY KEY,
    message_id INTEGER NOT NULL REFERENCES messages(id) ON DELETE CASCADE,
    generation_id INTEGER NOT NULL REFERENCES mailbox_generations(id) ON DELETE CASCADE,
    uid INTEGER NOT NULL,
    flags_json TEXT NOT NULL DEFAULT '[]',
    labels_json TEXT NOT NULL DEFAULT '[]',
    internal_date TEXT,
    rfc822_size INTEGER NOT NULL DEFAULT 0,
    modseq INTEGER,
    selected_for_raw INTEGER NOT NULL DEFAULT 1,
    fetch_status TEXT NOT NULL DEFAULT 'metadata',
    last_error TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    UNIQUE(generation_id, uid)
);

CREATE INDEX IF NOT EXISTS idx_occurrence_pending ON message_occurrences(selected_for_raw, fetch_status);
CREATE INDEX IF NOT EXISTS idx_occurrence_message ON message_occurrences(message_id);

CREATE TABLE IF NOT EXISTS message_participants (
    id INTEGER PRIMARY KEY,
    message_id INTEGER NOT NULL REFERENCES messages(id) ON DELETE CASCADE,
    role TEXT NOT NULL,
    ordinal INTEGER NOT NULL,
    name TEXT NOT NULL DEFAULT '',
    address TEXT NOT NULL,
    domain TEXT,
    UNIQUE(message_id, role, ordinal)
);

CREATE INDEX IF NOT EXISTS idx_participants_address ON message_participants(address);
CREATE INDEX IF NOT EXISTS idx_participants_domain ON message_participants(domain);

CREATE TABLE IF NOT EXISTS message_bodies (
    message_id INTEGER PRIMARY KEY REFERENCES messages(id) ON DELETE CASCADE,
    plain_text TEXT,
    html_text TEXT,
    html_visible_text TEXT,
    charsets_json TEXT NOT NULL DEFAULT '[]'
);

CREATE TABLE IF NOT EXISTS blobs (
    sha256 TEXT PRIMARY KEY,
    size_bytes INTEGER NOT NULL,
    detected_mime_type TEXT NOT NULL,
    storage_path TEXT NOT NULL,
    first_seen_at TEXT NOT NULL,
    last_verified_at TEXT
);

CREATE TABLE IF NOT EXISTS message_parts (
    id INTEGER PRIMARY KEY,
    message_id INTEGER NOT NULL REFERENCES messages(id) ON DELETE CASCADE,
    part_path TEXT NOT NULL,
    parent_part_path TEXT,
    role TEXT NOT NULL,
    declared_mime_type TEXT NOT NULL,
    detected_mime_type TEXT,
    content_disposition TEXT,
    content_id TEXT,
    filename_original TEXT,
    filename_safe TEXT,
    charset TEXT,
    transfer_encoding TEXT,
    size_bytes INTEGER NOT NULL DEFAULT 0,
    sha256 TEXT REFERENCES blobs(sha256),
    blob_path TEXT,
    headers_json TEXT NOT NULL DEFAULT '{}',
    defects_json TEXT NOT NULL DEFAULT '[]',
    UNIQUE(message_id, part_path)
);

CREATE INDEX IF NOT EXISTS idx_parts_sha ON message_parts(sha256);
CREATE INDEX IF NOT EXISTS idx_parts_role ON message_parts(role);

CREATE TABLE IF NOT EXISTS message_relations (
    id INTEGER PRIMARY KEY,
    source_message_id INTEGER NOT NULL REFERENCES messages(id) ON DELETE CASCADE,
    target_message_id INTEGER NOT NULL REFERENCES messages(id) ON DELETE CASCADE,
    relation_type TEXT NOT NULL,
    evidence_type TEXT NOT NULL,
    confidence REAL NOT NULL,
    created_at TEXT NOT NULL,
    UNIQUE(source_message_id, target_message_id, relation_type, evidence_type)
);

CREATE TABLE IF NOT EXISTS bandwidth_events (
    id INTEGER PRIMARY KEY,
    account_id INTEGER NOT NULL REFERENCES accounts(id) ON DELETE CASCADE,
    occurred_at TEXT NOT NULL,
    byte_count INTEGER NOT NULL,
    kind TEXT NOT NULL,
    run_id INTEGER REFERENCES runs(id) ON DELETE SET NULL
);

CREATE INDEX IF NOT EXISTS idx_bandwidth_window ON bandwidth_events(account_id, occurred_at);

CREATE TABLE IF NOT EXISTS failures (
    id INTEGER PRIMARY KEY,
    run_id INTEGER REFERENCES runs(id) ON DELETE SET NULL,
    occurrence_id INTEGER REFERENCES message_occurrences(id) ON DELETE SET NULL,
    stage TEXT NOT NULL,
    error_type TEXT NOT NULL,
    error_message TEXT NOT NULL,
    occurred_at TEXT NOT NULL
);
"""


def _now() -> str:
    return datetime.now(UTC).isoformat()


def _json(value: Any) -> str:
    return safe_json_dumps(value, ensure_ascii=False, sort_keys=True)


class ArchiveRepository:
    def __init__(self, path: Path) -> None:
        self.path = path
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.connection = sqlite3.connect(path, timeout=30.0)
        self.connection.row_factory = sqlite3.Row
        self.connection.execute("PRAGMA foreign_keys=ON")
        self.connection.execute("PRAGMA journal_mode=WAL")
        self.connection.execute("PRAGMA synchronous=NORMAL")
        self.connection.execute("PRAGMA busy_timeout=30000")
        self.connection.execute("PRAGMA temp_store=MEMORY")
        self.connection.executescript(_SCHEMA)
        self.connection.execute(
            "INSERT OR REPLACE INTO schema_meta(key, value) VALUES('schema_version', ?)",
            (str(_SCHEMA_VERSION),),
        )
        self.connection.commit()

    def __enter__(self) -> ArchiveRepository:
        return self

    def __exit__(self, exc_type: object, exc: object, tb: object) -> None:
        self.close()

    def close(self) -> None:
        self.connection.close()

    @contextmanager
    def transaction(self) -> Iterator[sqlite3.Connection]:
        try:
            self.connection.execute("BEGIN IMMEDIATE")
            yield self.connection
            self.connection.commit()
        except Exception:
            self.connection.rollback()
            raise

    def get_or_create_account(self, config: MailVaultConfig, provider: ProviderKind) -> int:
        now = _now()
        with self.transaction() as conn:
            conn.execute(
                """
                INSERT INTO accounts(archive_id, email, host, port, provider_kind, tls_mode, created_at, updated_at)
                VALUES(?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(email, host, port) DO UPDATE SET
                    provider_kind=excluded.provider_kind,
                    tls_mode=excluded.tls_mode,
                    updated_at=excluded.updated_at
                """,
                (
                    str(uuid4()),
                    config.account.casefold(),
                    config.host.casefold(),
                    config.port,
                    provider.value,
                    config.tls_mode.value,
                    now,
                    now,
                ),
            )
            row = conn.execute(
                "SELECT id FROM accounts WHERE email=? AND host=? AND port=?",
                (config.account.casefold(), config.host.casefold(), config.port),
            ).fetchone()
            assert row is not None
            return int(row["id"])

    def record_capabilities(self, account_id: int, capabilities: ServerCapabilities) -> None:
        self.connection.execute(
            "INSERT INTO server_snapshots(account_id, capabilities_json, observed_at) VALUES(?, ?, ?)",
            (account_id, _json(list(capabilities.raw)), _now()),
        )
        self.connection.commit()

    def upsert_mailbox(
        self,
        account_id: int,
        mailbox: MailboxInfo,
        *,
        mailbox_object_id: str | None = None,
    ) -> int:
        now = _now()
        with self.transaction() as conn:
            conn.execute(
                """
                INSERT INTO mailboxes(account_id, name, delimiter, flags_json, mailbox_object_id, created_at, updated_at)
                VALUES(?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(account_id, name) DO UPDATE SET
                    delimiter=excluded.delimiter,
                    flags_json=excluded.flags_json,
                    mailbox_object_id=COALESCE(excluded.mailbox_object_id, mailboxes.mailbox_object_id),
                    updated_at=excluded.updated_at
                """,
                (
                    account_id,
                    sanitize_text(mailbox.name),
                    sanitize_optional_text(mailbox.delimiter),
                    _json(list(mailbox.flags)),
                    sanitize_optional_text(mailbox_object_id),
                    now,
                    now,
                ),
            )
            row = conn.execute(
                "SELECT id FROM mailboxes WHERE account_id=? AND name=?",
                (account_id, sanitize_text(mailbox.name)),
            ).fetchone()
            assert row is not None
            return int(row["id"])

    def get_or_create_generation(
        self,
        mailbox_id: int,
        uidvalidity: int,
        highest_uid: int,
        highest_modseq: int | None,
    ) -> SelectedMailbox:
        now = _now()
        with self.transaction() as conn:
            conn.execute(
                """
                INSERT INTO mailbox_generations(
                    mailbox_id, uidvalidity, highest_uid, highest_modseq, created_at, updated_at
                ) VALUES(?, ?, ?, ?, ?, ?)
                ON CONFLICT(mailbox_id, uidvalidity) DO UPDATE SET
                    highest_modseq=COALESCE(excluded.highest_modseq, mailbox_generations.highest_modseq),
                    updated_at=excluded.updated_at
                """,
                (mailbox_id, uidvalidity, 0, highest_modseq, now, now),
            )
            row = conn.execute(
                """
                SELECT g.*, m.name, m.mailbox_object_id
                FROM mailbox_generations g JOIN mailboxes m ON m.id=g.mailbox_id
                WHERE g.mailbox_id=? AND g.uidvalidity=?
                """,
                (mailbox_id, uidvalidity),
            ).fetchone()
            assert row is not None
            return SelectedMailbox(
                mailbox_id=mailbox_id,
                generation_id=int(row["id"]),
                name=str(row["name"]),
                uidvalidity=uidvalidity,
                highest_uid=int(row["highest_uid"]),
                highest_modseq=int(row["highest_modseq"])
                if row["highest_modseq"] is not None
                else None,
                mailbox_object_id=cast(str | None, row["mailbox_object_id"]),
            )

    def get_or_create_scan_checkpoint(
        self,
        generation_id: int,
        selection_key: str,
    ) -> tuple[int, int | None]:
        now = _now()
        with self.transaction() as conn:
            conn.execute(
                """
                INSERT INTO scan_checkpoints(
                    generation_id, selection_key, highest_uid, highest_modseq,
                    created_at, updated_at
                ) VALUES(?, ?, 0, NULL, ?, ?)
                ON CONFLICT(generation_id, selection_key) DO NOTHING
                """,
                (generation_id, selection_key, now, now),
            )
            row = conn.execute(
                """
                SELECT highest_uid, highest_modseq
                FROM scan_checkpoints
                WHERE generation_id=? AND selection_key=?
                """,
                (generation_id, selection_key),
            ).fetchone()
            assert row is not None
            return (
                int(row["highest_uid"]),
                int(row["highest_modseq"]) if row["highest_modseq"] is not None else None,
            )

    def update_scan_checkpoint(
        self,
        generation_id: int,
        selection_key: str,
        *,
        highest_uid: int,
        highest_modseq: int | None,
    ) -> None:
        now = _now()
        self.connection.execute(
            """
            UPDATE scan_checkpoints SET
                highest_uid=MAX(highest_uid, ?),
                highest_modseq=CASE
                    WHEN ? IS NULL THEN highest_modseq
                    WHEN highest_modseq IS NULL THEN ?
                    ELSE MAX(highest_modseq, ?)
                END,
                last_scan_at=?, updated_at=?
            WHERE generation_id=? AND selection_key=?
            """,
            (
                highest_uid,
                highest_modseq,
                highest_modseq,
                highest_modseq,
                now,
                now,
                generation_id,
                selection_key,
            ),
        )
        self.connection.commit()

    def update_generation_checkpoint(
        self,
        generation_id: int,
        *,
        highest_uid: int,
        highest_modseq: int | None,
    ) -> None:
        self.connection.execute(
            """
            UPDATE mailbox_generations SET
                highest_uid=MAX(highest_uid, ?),
                highest_modseq=COALESCE(?, highest_modseq),
                last_scan_at=?, updated_at=?
            WHERE id=?
            """,
            (highest_uid, highest_modseq, _now(), _now(), generation_id),
        )
        self.connection.commit()

    def start_run(self, account_id: int, scope: str, query: str | None) -> int:
        cursor = self.connection.execute(
            """
            INSERT INTO runs(account_id, started_at, status, scope, query_text)
            VALUES(?, ?, 'running', ?, ?)
            """,
            (account_id, _now(), scope, query),
        )
        self.connection.commit()
        assert cursor.lastrowid is not None
        return int(cursor.lastrowid)

    def finish_run(
        self,
        run_id: int,
        *,
        status: str,
        mailboxes_scanned: int,
        metadata_scanned: int,
        raw_archived: int,
        bytes_downloaded: int,
        errors: int,
        stop_reason: str | None,
    ) -> None:
        self.connection.execute(
            """
            UPDATE runs SET finished_at=?, status=?, mailboxes_scanned=?, metadata_scanned=?,
                raw_archived=?, bytes_downloaded=?, errors=?, stop_reason=? WHERE id=?
            """,
            (
                _now(),
                status,
                mailboxes_scanned,
                metadata_scanned,
                raw_archived,
                bytes_downloaded,
                errors,
                sanitize_optional_text(stop_reason),
                run_id,
            ),
        )
        self.connection.commit()

    def upsert_metadata(
        self,
        account_id: int,
        generation_id: int,
        record: MetadataRecord,
        headers: ParsedHeaders,
        stable_identity: tuple[str, str] | None,
        thread_identity: tuple[str, str] | None,
        *,
        selected_for_raw: bool,
    ) -> tuple[int, int]:
        now = _now()
        with self.transaction() as conn:
            occurrence = conn.execute(
                "SELECT id, message_id FROM message_occurrences WHERE generation_id=? AND uid=?",
                (generation_id, record.uid),
            ).fetchone()
            if occurrence is not None:
                message_id = int(occurrence["message_id"])
                occurrence_id = int(occurrence["id"])
            else:
                message_id = self._find_or_create_message(
                    conn,
                    account_id,
                    stable_identity,
                    thread_identity,
                    headers,
                    now,
                )
                cursor = conn.execute(
                    """
                    INSERT INTO message_occurrences(
                        message_id, generation_id, uid, flags_json, labels_json, internal_date,
                        rfc822_size, modseq, selected_for_raw, created_at, updated_at
                    ) VALUES(?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        message_id,
                        generation_id,
                        record.uid,
                        _json(list(record.flags)),
                        _json(list(record.provider.labels)),
                        record.internal_date.isoformat() if record.internal_date else None,
                        record.rfc822_size,
                        record.modseq,
                        int(selected_for_raw),
                        now,
                        now,
                    ),
                )
                assert cursor.lastrowid is not None
                occurrence_id = int(cursor.lastrowid)

            conn.execute(
                """
                UPDATE messages SET
                    provider_thread_namespace=COALESCE(?, provider_thread_namespace),
                    provider_thread_value=COALESCE(?, provider_thread_value),
                    rfc_message_id=COALESCE(?, rfc_message_id),
                    in_reply_to=?, references_json=?, subject_raw=?, subject_normalized=?,
                    return_path=?, delivered_to_json=?, x_original_to_json=?, list_id=?,
                    header_date=?, content_type_header=?, authentication_results_json=?,
                    received_headers_json=?, headers_json=?, updated_at=?
                WHERE id=?
                """,
                (
                    thread_identity[0] if thread_identity else None,
                    thread_identity[1] if thread_identity else None,
                    headers.rfc_message_id,
                    headers.in_reply_to,
                    _json(list(headers.references)),
                    sanitize_text(headers.subject_raw),
                    sanitize_text(headers.subject_normalized),
                    sanitize_optional_text(headers.return_path),
                    _json(list(headers.delivered_to)),
                    _json(list(headers.x_original_to)),
                    sanitize_optional_text(headers.list_id),
                    headers.header_date.isoformat() if headers.header_date else None,
                    sanitize_optional_text(headers.content_type),
                    _json(list(headers.authentication_results)),
                    _json(list(headers.received_headers)),
                    _json(headers.all_headers),
                    now,
                    message_id,
                ),
            )
            conn.execute(
                """
                UPDATE message_occurrences SET flags_json=?, labels_json=?, internal_date=?,
                    rfc822_size=?, modseq=?, selected_for_raw=?, updated_at=? WHERE id=?
                """,
                (
                    _json(list(record.flags)),
                    _json(list(record.provider.labels)),
                    record.internal_date.isoformat() if record.internal_date else None,
                    record.rfc822_size,
                    record.modseq,
                    int(selected_for_raw),
                    now,
                    occurrence_id,
                ),
            )
            self._add_identity(conn, account_id, message_id, stable_identity, now)
            if headers.rfc_message_id:
                self._add_identity(
                    conn,
                    account_id,
                    message_id,
                    ("rfc-message-id", headers.rfc_message_id.casefold()),
                    now,
                    allow_conflict=True,
                )
            self._replace_participants(conn, message_id, headers)
            return message_id, occurrence_id

    def _find_or_create_message(
        self,
        conn: sqlite3.Connection,
        account_id: int,
        stable_identity: tuple[str, str] | None,
        thread_identity: tuple[str, str] | None,
        headers: ParsedHeaders,
        now: str,
    ) -> int:
        if stable_identity:
            row = conn.execute(
                """
                SELECT message_id FROM message_identities
                WHERE account_id=? AND namespace=? AND value=?
                """,
                (account_id, stable_identity[0], stable_identity[1]),
            ).fetchone()
            if row is not None:
                return int(row["message_id"])
        cursor = conn.execute(
            """
            INSERT INTO messages(
                archive_id, account_id, provider_thread_namespace, provider_thread_value,
                rfc_message_id, in_reply_to, references_json, subject_raw, subject_normalized,
                return_path, delivered_to_json, x_original_to_json, list_id, header_date,
                content_type_header, authentication_results_json, received_headers_json,
                headers_json, created_at, updated_at
            ) VALUES(?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                str(uuid4()),
                account_id,
                thread_identity[0] if thread_identity else None,
                thread_identity[1] if thread_identity else None,
                headers.rfc_message_id,
                headers.in_reply_to,
                _json(list(headers.references)),
                sanitize_text(headers.subject_raw),
                sanitize_text(headers.subject_normalized),
                sanitize_optional_text(headers.return_path),
                _json(list(headers.delivered_to)),
                _json(list(headers.x_original_to)),
                sanitize_optional_text(headers.list_id),
                headers.header_date.isoformat() if headers.header_date else None,
                sanitize_optional_text(headers.content_type),
                _json(list(headers.authentication_results)),
                _json(list(headers.received_headers)),
                _json(headers.all_headers),
                now,
                now,
            ),
        )
        assert cursor.lastrowid is not None
        return int(cursor.lastrowid)

    @staticmethod
    def _add_identity(
        conn: sqlite3.Connection,
        account_id: int,
        message_id: int,
        identity: tuple[str, str] | None,
        now: str,
        *,
        allow_conflict: bool = False,
    ) -> None:
        if not identity or not identity[1]:
            return
        sql = (
            "INSERT OR IGNORE INTO message_identities(account_id, message_id, namespace, value, created_at) "
            "VALUES(?, ?, ?, ?, ?)"
            if allow_conflict
            else "INSERT INTO message_identities(account_id, message_id, namespace, value, created_at) "
            "VALUES(?, ?, ?, ?, ?) ON CONFLICT(account_id, namespace, value) DO NOTHING"
        )
        conn.execute(sql, (account_id, message_id, identity[0], identity[1], now))

    @staticmethod
    def _replace_participants(
        conn: sqlite3.Connection,
        message_id: int,
        headers: ParsedHeaders,
    ) -> None:
        conn.execute("DELETE FROM message_participants WHERE message_id=?", (message_id,))
        groups = {
            "from": headers.from_values,
            "sender": headers.sender_values,
            "reply_to": headers.reply_to_values,
            "to": headers.to_values,
            "cc": headers.cc_values,
            "bcc": headers.bcc_values,
        }
        for role, values in groups.items():
            for ordinal, value in enumerate(values):
                conn.execute(
                    """
                    INSERT INTO message_participants(message_id, role, ordinal, name, address, domain)
                    VALUES(?, ?, ?, ?, ?, ?)
                    """,
                    (message_id, role, ordinal, value.name, value.address, value.domain),
                )

    def pending_raw_occurrences(self, account_id: int) -> list[sqlite3.Row]:
        return list(
            self.connection.execute(
                """
                SELECT
                    o.id AS occurrence_id,
                    o.message_id,
                    o.uid,
                    o.rfc822_size,
                    g.id AS generation_id,
                    g.uidvalidity,
                    mb.name AS mailbox_name,
                    m.archive_id,
                    m.subject_raw
                FROM message_occurrences o
                JOIN messages m ON m.id=o.message_id
                JOIN mailbox_generations g ON g.id=o.generation_id
                JOIN mailboxes mb ON mb.id=g.mailbox_id
                WHERE m.account_id=?
                  AND o.selected_for_raw=1
                  AND m.raw_path IS NULL
                  AND o.id=(
                      SELECT MIN(o2.id)
                      FROM message_occurrences o2
                      WHERE o2.message_id=o.message_id AND o2.selected_for_raw=1
                  )
                ORDER BY COALESCE(o.internal_date, ''), o.uid
                """,
                (account_id,),
            ).fetchall()
        )

    def occurrence_by_id(self, occurrence_id: int) -> sqlite3.Row | None:
        return cast(
            sqlite3.Row | None,
            self.connection.execute(
                """
                SELECT o.*, g.uidvalidity, mb.name AS mailbox_name, m.account_id, m.archive_id
                FROM message_occurrences o
                JOIN mailbox_generations g ON g.id=o.generation_id
                JOIN mailboxes mb ON mb.id=g.mailbox_id
                JOIN messages m ON m.id=o.message_id
                WHERE o.id=?
                """,
                (occurrence_id,),
            ).fetchone(),
        )

    def attach_raw_and_maybe_merge(
        self,
        message_id: int,
        *,
        raw_path: str,
        raw_sha256: str,
        raw_size: int,
    ) -> int:
        now = _now()
        with self.transaction() as conn:
            row = conn.execute(
                "SELECT account_id FROM messages WHERE id=?", (message_id,)
            ).fetchone()
            if row is None:
                raise ValueError(f"Unknown message id {message_id}")
            account_id = int(row["account_id"])
            duplicate = conn.execute(
                """
                SELECT id FROM messages
                WHERE account_id=? AND raw_sha256=? AND id<>?
                ORDER BY id LIMIT 1
                """,
                (account_id, raw_sha256, message_id),
            ).fetchone()
            canonical_id = int(duplicate["id"]) if duplicate is not None else message_id
            if canonical_id != message_id:
                self._merge_messages(conn, canonical_id, message_id)
            conn.execute(
                """
                UPDATE messages SET raw_path=?, raw_sha256=?, raw_size_bytes=?, raw_archived_at=?,
                    updated_at=? WHERE id=?
                """,
                (raw_path, raw_sha256, raw_size, now, now, canonical_id),
            )
            self._add_identity(
                conn,
                account_id,
                canonical_id,
                ("raw-sha256", raw_sha256),
                now,
                allow_conflict=True,
            )
            return canonical_id

    @staticmethod
    def _merge_messages(conn: sqlite3.Connection, target_id: int, source_id: int) -> None:
        conn.execute(
            "UPDATE message_occurrences SET message_id=? WHERE message_id=?",
            (target_id, source_id),
        )
        identities = conn.execute(
            "SELECT account_id, namespace, value, created_at FROM message_identities WHERE message_id=?",
            (source_id,),
        ).fetchall()
        for identity in identities:
            conn.execute(
                """
                INSERT OR IGNORE INTO message_identities(account_id, message_id, namespace, value, created_at)
                VALUES(?, ?, ?, ?, ?)
                """,
                (
                    identity["account_id"],
                    target_id,
                    identity["namespace"],
                    identity["value"],
                    identity["created_at"],
                ),
            )
        conn.execute("DELETE FROM messages WHERE id=?", (source_id,))

    def save_parsed_message(
        self,
        message_id: int,
        parsed: ParsedMessage,
        parts_with_blob_records: Sequence[dict[str, Any]],
    ) -> None:
        now = _now()
        with self.transaction() as conn:
            conn.execute(
                """
                UPDATE messages SET mime_parsed_at=?, parse_defects_json=?, updated_at=? WHERE id=?
                """,
                (_now(), _json(parsed.defects), now, message_id),
            )
            conn.execute(
                """
                INSERT INTO message_bodies(message_id, plain_text, html_text, html_visible_text, charsets_json)
                VALUES(?, ?, ?, ?, ?)
                ON CONFLICT(message_id) DO UPDATE SET
                    plain_text=excluded.plain_text,
                    html_text=excluded.html_text,
                    html_visible_text=excluded.html_visible_text,
                    charsets_json=excluded.charsets_json
                """,
                (
                    message_id,
                    sanitize_optional_text(parsed.plain_text),
                    sanitize_optional_text(parsed.html_text),
                    sanitize_optional_text(parsed.html_visible_text),
                    _json(list(parsed.charsets)),
                ),
            )
            conn.execute("DELETE FROM message_parts WHERE message_id=?", (message_id,))
            for item in parts_with_blob_records:
                if item.get("sha256"):
                    conn.execute(
                        """
                        INSERT INTO blobs(sha256, size_bytes, detected_mime_type, storage_path, first_seen_at)
                        VALUES(?, ?, ?, ?, ?)
                        ON CONFLICT(sha256) DO UPDATE SET
                            detected_mime_type=excluded.detected_mime_type,
                            storage_path=excluded.storage_path
                        """,
                        (
                            item["sha256"],
                            item["size_bytes"],
                            item["detected_mime_type"],
                            item["blob_path"],
                            now,
                        ),
                    )
                conn.execute(
                    """
                    INSERT INTO message_parts(
                        message_id, part_path, parent_part_path, role, declared_mime_type,
                        detected_mime_type, content_disposition, content_id, filename_original,
                        filename_safe, charset, transfer_encoding, size_bytes, sha256, blob_path,
                        headers_json, defects_json
                    ) VALUES(?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        message_id,
                        item["part_path"],
                        item.get("parent_part_path"),
                        sanitize_text(str(item["role"])),
                        sanitize_text(str(item["declared_mime_type"])),
                        sanitize_optional_text(item.get("detected_mime_type")),
                        sanitize_optional_text(item.get("content_disposition")),
                        sanitize_optional_text(item.get("content_id")),
                        sanitize_optional_text(item.get("filename_original")),
                        sanitize_optional_text(item.get("filename_safe")),
                        sanitize_optional_text(item.get("charset")),
                        sanitize_optional_text(item.get("transfer_encoding")),
                        item.get("size_bytes", 0),
                        item.get("sha256"),
                        item.get("blob_path"),
                        _json(item.get("headers", {})),
                        _json(item.get("defects", [])),
                    ),
                )
            conn.execute(
                "UPDATE message_occurrences SET fetch_status='complete', last_error=NULL, updated_at=? WHERE message_id=?",
                (now, message_id),
            )
            self._link_rfc_relations(conn, message_id)

    @staticmethod
    def _link_rfc_relations(conn: sqlite3.Connection, message_id: int) -> None:
        source = conn.execute(
            "SELECT account_id, in_reply_to, references_json FROM messages WHERE id=?",
            (message_id,),
        ).fetchone()
        if source is None:
            return
        account_id = int(source["account_id"])
        candidates: list[tuple[str, str, float]] = []
        if source["in_reply_to"]:
            candidates.append((str(source["in_reply_to"]), "reply_to", 1.0))
        try:
            refs = json.loads(str(source["references_json"]))
        except json.JSONDecodeError:
            refs = []
        for value in refs:
            candidates.append((str(value), "references", 1.0))
        for value, relation_type, confidence in candidates:
            target = conn.execute(
                """
                SELECT message_id FROM message_identities
                WHERE account_id=? AND namespace='rfc-message-id' AND value=?
                """,
                (account_id, value.casefold()),
            ).fetchone()
            if target is None or int(target["message_id"]) == message_id:
                continue
            conn.execute(
                """
                INSERT OR IGNORE INTO message_relations(
                    source_message_id, target_message_id, relation_type, evidence_type, confidence, created_at
                ) VALUES(?, ?, ?, 'rfc5322-header', ?, ?)
                """,
                (message_id, int(target["message_id"]), relation_type, confidence, _now()),
            )

    def mark_fetch_error(self, occurrence_id: int, error: str) -> None:
        self.connection.execute(
            "UPDATE message_occurrences SET fetch_status='error', last_error=?, updated_at=? WHERE id=?",
            (sanitize_text(error)[:4000], _now(), occurrence_id),
        )
        self.connection.commit()

    def record_failure(
        self,
        run_id: int,
        occurrence_id: int | None,
        stage: str,
        error: BaseException,
    ) -> None:
        self.connection.execute(
            """
            INSERT INTO failures(run_id, occurrence_id, stage, error_type, error_message, occurred_at)
            VALUES(?, ?, ?, ?, ?, ?)
            """,
            (
                run_id,
                occurrence_id,
                sanitize_text(stage),
                type(error).__name__,
                sanitize_text(str(error))[:4000],
                _now(),
            ),
        )
        self.connection.commit()

    def record_bandwidth(self, account_id: int, byte_count: int, kind: str, run_id: int) -> None:
        self.connection.execute(
            "INSERT INTO bandwidth_events(account_id, occurred_at, byte_count, kind, run_id) VALUES(?, ?, ?, ?, ?)",
            (account_id, _now(), byte_count, kind, run_id),
        )
        self.connection.commit()

    def rolling_bandwidth(self, account_id: int, hours: int = 24) -> int:
        cutoff = (datetime.now(UTC) - timedelta(hours=hours)).isoformat()
        row = self.connection.execute(
            "SELECT COALESCE(SUM(byte_count), 0) AS total FROM bandwidth_events WHERE account_id=? AND occurred_at>=?",
            (account_id, cutoff),
        ).fetchone()
        assert row is not None
        return int(row["total"])

    def message_document(self, message_id: int) -> dict[str, Any]:
        message = self.connection.execute(
            "SELECT * FROM messages WHERE id=?", (message_id,)
        ).fetchone()
        if message is None:
            raise ValueError(f"Unknown message id {message_id}")
        return {
            "schema_version": "firexcore.mailvault.message.v2",
            "message": _row_to_dict(message),
            "identities": [
                _row_to_dict(row)
                for row in self.connection.execute(
                    "SELECT * FROM message_identities WHERE message_id=? ORDER BY namespace, value",
                    (message_id,),
                )
            ],
            "occurrences": [
                _row_to_dict(row)
                for row in self.connection.execute(
                    """
                    SELECT o.*, mb.name AS mailbox_name, g.uidvalidity
                    FROM message_occurrences o
                    JOIN mailbox_generations g ON g.id=o.generation_id
                    JOIN mailboxes mb ON mb.id=g.mailbox_id
                    WHERE o.message_id=? ORDER BY mb.name, o.uid
                    """,
                    (message_id,),
                )
            ],
            "participants": [
                _row_to_dict(row)
                for row in self.connection.execute(
                    "SELECT * FROM message_participants WHERE message_id=? ORDER BY role, ordinal",
                    (message_id,),
                )
            ],
            "parts": [
                _row_to_dict(row)
                for row in self.connection.execute(
                    "SELECT * FROM message_parts WHERE message_id=? ORDER BY part_path",
                    (message_id,),
                )
            ],
            "relations": [
                _row_to_dict(row)
                for row in self.connection.execute(
                    "SELECT * FROM message_relations WHERE source_message_id=? ORDER BY id",
                    (message_id,),
                )
            ],
        }

    def stats(self, account_id: int | None = None) -> dict[str, int]:
        result: dict[str, int] = {}
        if account_id is None:
            message_where = ""
            occurrence_where = ""
            params: tuple[int, ...] = ()
        else:
            message_where = " WHERE account_id=?"
            occurrence_where = " WHERE m.account_id=?"
            params = (account_id,)
        queries = {
            "messages": f"SELECT COUNT(*) FROM messages{message_where}",
            "raw_messages": f"SELECT COUNT(*) FROM messages{message_where}{' AND' if message_where else ' WHERE'} raw_path IS NOT NULL",
            "raw_bytes": f"SELECT COALESCE(SUM(raw_size_bytes),0) FROM messages{message_where}",
            "occurrences": (
                "SELECT COUNT(*) FROM message_occurrences o JOIN messages m ON m.id=o.message_id"
                + occurrence_where
            ),
        }
        for key, query in queries.items():
            row = self.connection.execute(query, params).fetchone()
            result[key] = int(row[0]) if row is not None else 0
        result["parts"] = int(
            self.connection.execute("SELECT COUNT(*) FROM message_parts").fetchone()[0]
        )
        result["blobs"] = int(self.connection.execute("SELECT COUNT(*) FROM blobs").fetchone()[0])
        result["blob_bytes"] = int(
            self.connection.execute("SELECT COALESCE(SUM(size_bytes),0) FROM blobs").fetchone()[0]
        )
        result["duplicate_part_occurrences"] = int(
            self.connection.execute(
                "SELECT COALESCE(SUM(c-1),0) FROM (SELECT COUNT(*) c FROM message_parts WHERE sha256 IS NOT NULL GROUP BY sha256 HAVING c>1)"
            ).fetchone()[0]
        )
        return result

    def find_account_id(self, email: str) -> int | None:
        row = self.connection.execute(
            "SELECT id FROM accounts WHERE email=? ORDER BY id LIMIT 1", (email.casefold(),)
        ).fetchone()
        return int(row["id"]) if row is not None else None

    def table_rows(self, table: str) -> Iterable[sqlite3.Row]:
        order_columns = {
            "accounts": "id",
            "mailboxes": "id",
            "mailbox_generations": "id",
            "messages": "id",
            "message_identities": "id",
            "message_occurrences": "id",
            "message_participants": "id",
            "message_bodies": "message_id",
            "message_parts": "id",
            "message_relations": "id",
            "blobs": "sha256",
            "failures": "id",
            "runs": "id",
        }
        order_column = order_columns.get(table)
        if order_column is None:
            raise ValueError(f"Unsupported export table: {table}")
        return self.connection.execute(f"SELECT * FROM {table} ORDER BY {order_column}")

    def integrity_messages(self) -> list[sqlite3.Row]:
        return list(
            self.connection.execute(
                "SELECT id, archive_id, raw_path, raw_sha256, raw_size_bytes FROM messages WHERE raw_path IS NOT NULL"
            ).fetchall()
        )

    def integrity_blobs(self) -> list[sqlite3.Row]:
        return list(self.connection.execute("SELECT * FROM blobs").fetchall())

    def mark_blob_verified(self, sha256: str) -> None:
        self.connection.execute(
            "UPDATE blobs SET last_verified_at=? WHERE sha256=?", (_now(), sha256)
        )
        self.connection.commit()

    def procurement_rows(self) -> Iterable[sqlite3.Row]:
        return self.connection.execute(
            """
            SELECT
                m.id AS message_id,
                m.archive_id,
                m.rfc_message_id,
                m.provider_thread_namespace,
                m.provider_thread_value,
                m.subject_raw,
                m.subject_normalized,
                m.header_date,
                m.raw_sha256,
                m.raw_path,
                b.plain_text,
                b.html_visible_text,
                p.id AS part_id,
                p.part_path,
                p.role,
                p.filename_original,
                p.declared_mime_type,
                p.detected_mime_type,
                p.sha256 AS part_sha256,
                p.blob_path,
                p.size_bytes,
                o.internal_date,
                o.labels_json,
                mb.name AS mailbox_name
            FROM messages m
            LEFT JOIN message_bodies b ON b.message_id=m.id
            LEFT JOIN message_parts p ON p.message_id=m.id
            LEFT JOIN message_occurrences o ON o.id=(
                SELECT MIN(o2.id) FROM message_occurrences o2 WHERE o2.message_id=m.id
            )
            LEFT JOIN mailbox_generations g ON g.id=o.generation_id
            LEFT JOIN mailboxes mb ON mb.id=g.mailbox_id
            WHERE m.raw_path IS NOT NULL
            ORDER BY m.id, p.part_path
            """
        )


def _row_to_dict(row: sqlite3.Row) -> dict[str, Any]:
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
    return output
