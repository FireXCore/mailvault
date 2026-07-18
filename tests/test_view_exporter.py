from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from firexcore_mailvault import atomic, view_exporter
from firexcore_mailvault.repository import ArchiveRepository
from firexcore_mailvault.view_exporter import ViewExporter


def _row(**overrides: Any) -> dict[str, Any]:
    row: dict[str, Any] = {
        "archive_id": "78184d7d-1d47-421f-a4df-960b10629ee8",
        "part_id": 615,
        "part_path": "1.2",
        "filename_safe": "x" * 500 + ".pdf",
        "sha256": "a" * 64,
    }
    row.update(overrides)
    return row


def _seed_view_source(repository: ArchiveRepository, *, message_count: int = 3) -> None:
    connection = repository.connection
    now = "2026-07-18T00:00:00+00:00"
    connection.execute(
        """
        INSERT INTO accounts(
            id, archive_id, email, host, port, provider_kind, tls_mode, created_at, updated_at
        ) VALUES(1, 'account-1', 'user@example.org', 'imap.example.org', 993,
                 'generic_imap', 'implicit', ?, ?)
        """,
        (now, now),
    )
    connection.execute(
        """
        INSERT INTO mailboxes(
            id, account_id, name, delimiter, flags_json, created_at, updated_at
        ) VALUES(1, 1, 'INBOX', '/', '[]', ?, ?)
        """,
        (now, now),
    )
    connection.execute(
        """
        INSERT INTO mailbox_generations(
            id, mailbox_id, uidvalidity, created_at, updated_at
        ) VALUES(1, 1, 1, ?, ?)
        """,
        (now, now),
    )

    for index in range(1, message_count + 1):
        connection.execute(
            """
            INSERT INTO messages(
                id, archive_id, account_id, provider_thread_namespace,
                provider_thread_value, subject_raw, subject_normalized,
                header_date, raw_path, raw_sha256, raw_size_bytes,
                created_at, updated_at
            ) VALUES(?, ?, 1, 'test-thread', ?, ?, ?, ?, ?, ?, 100, ?, ?)
            """,
            (
                index,
                f"message-{index}",
                f"thread-{index % 2}",
                f"Subject {index}",
                f"subject {index}",
                f"202{index}-01-01T00:00:00+00:00",
                f"objects/raw/{index}.eml",
                str(index) * 64,
                now,
                now,
            ),
        )
        connection.execute(
            """
            INSERT INTO message_occurrences(
                id, message_id, generation_id, uid, labels_json, internal_date,
                rfc822_size, created_at, updated_at
            ) VALUES(?, ?, 1, ?, ?, ?, 100, ?, ?)
            """,
            (
                index,
                index,
                index,
                json.dumps(["INBOX", f"Label-{index % 2}"]),
                f"202{index}-01-01T00:00:00+00:00",
                now,
                now,
            ),
        )
        connection.execute(
            """
            INSERT INTO message_participants(
                message_id, role, ordinal, name, address, domain
            ) VALUES(?, 'from', 0, ?, ?, 'vendor.example')
            """,
            (index, f"Vendor {index}", f"vendor{index}@vendor.example"),
        )
        connection.execute(
            """
            INSERT INTO message_parts(
                id, message_id, part_path, role, declared_mime_type,
                detected_mime_type, filename_original, filename_safe,
                size_bytes, headers_json, defects_json
            ) VALUES(?, ?, '1', 'attachment', 'application/pdf',
                     'application/pdf', ?, ?, 50, '{}', '[]')
            """,
            (index, index, f"Document {index}.pdf", f"document-{index}.pdf"),
        )
    connection.commit()


def _exporter(root: Path, repository: ArchiveRepository) -> ViewExporter:
    return ViewExporter(repository, root, root / "views")


def test_pointer_filename_is_concise_deterministic_and_attachment_name_independent() -> None:
    first = ViewExporter._pointer_filename(_row())  # type: ignore[arg-type]
    second = ViewExporter._pointer_filename(_row())  # type: ignore[arg-type]

    assert first == second
    assert len(first) < 96
    assert first.endswith(".json")
    assert "x" * 20 not in first
    assert "part-615" in first


def test_pointer_filename_changes_when_part_identity_changes() -> None:
    first = ViewExporter._pointer_filename(_row())  # type: ignore[arg-type]
    second = ViewExporter._pointer_filename(  # type: ignore[arg-type]
        _row(part_id=616, part_path="1.3")
    )

    assert first != second


def test_view_segment_is_bounded_and_collision_resistant() -> None:
    first = ViewExporter._view_segment("a" * 300)
    second = ViewExporter._view_segment("a" * 299 + "b")

    assert len(first) == 64
    assert len(second) == 64
    assert first != second
    assert ViewExporter._view_segment("INBOX") == "INBOX"


def test_atomic_write_uses_short_temporary_prefix(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    captured: dict[str, Any] = {}
    original = atomic.tempfile.mkstemp

    def recording_mkstemp(*args: Any, **kwargs: Any) -> tuple[int, str]:
        captured.update(kwargs)
        return original(*args, **kwargs)

    monkeypatch.setattr(atomic.tempfile, "mkstemp", recording_mkstemp)

    target = tmp_path / "atomic-target.json"
    atomic.atomic_write_json(target, {"ok": True})

    assert target.is_file()
    assert captured["prefix"] == ".mv-"
    assert captured["suffix"] == ".tmp"


def test_interrupted_build_resumes_without_discarding_completed_rows(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = tmp_path / "archive"
    database = root / "database" / "mailvault.sqlite3"
    monkeypatch.setattr(view_exporter, "_PROGRESS_ROW_INTERVAL", 1)

    with ArchiveRepository(database) as repository:
        _seed_view_source(repository)
        views = root / "views"
        views.mkdir(parents=True)
        (views / "old-view.json").write_text("old", encoding="utf-8")

        def interrupt(event: str, payload: dict[str, object]) -> None:
            if event == "advanced" and payload["processed_rows"] == 2:
                raise KeyboardInterrupt

        with pytest.raises(KeyboardInterrupt):
            _exporter(root, repository).rebuild(progress=interrupt)

    checkpoint = root / "state" / "views-rebuild-v1.json"
    staging = root / "state" / "views-rebuild-staging-v3"
    state = json.loads(checkpoint.read_text(encoding="utf-8"))
    assert state["processed_rows"] == 2
    assert staging.is_dir()
    assert (root / "views" / "old-view.json").is_file()

    events: list[tuple[str, dict[str, object]]] = []
    with ArchiveRepository(database) as repository:
        result = _exporter(root, repository).rebuild(
            progress=lambda event, payload: events.append((event, payload))
        )

    assert result.resumed is True
    assert result.up_to_date is False
    assert result.rows_processed == 3
    assert result.total_pointers == 18
    assert result.pointers_written == 18
    assert not checkpoint.exists()
    assert not staging.exists()
    assert not (root / "views" / "old-view.json").exists()
    assert (root / "views" / "_mailvault_views.json").is_file()
    assert any(
        event == "build_started" and payload["processed_rows"] == 2 for event, payload in events
    )


def test_changed_source_invalidates_incomplete_checkpoint(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = tmp_path / "archive"
    database = root / "database" / "mailvault.sqlite3"
    monkeypatch.setattr(view_exporter, "_PROGRESS_ROW_INTERVAL", 1)

    with ArchiveRepository(database) as repository:
        _seed_view_source(repository)

        def interrupt(event: str, payload: dict[str, object]) -> None:
            if event == "advanced" and payload["processed_rows"] == 1:
                raise KeyboardInterrupt

        with pytest.raises(KeyboardInterrupt):
            _exporter(root, repository).rebuild(progress=interrupt)

    with ArchiveRepository(database) as repository:
        repository.connection.execute(
            "UPDATE messages SET subject_raw='Changed subject', updated_at=? WHERE id=1",
            ("2026-07-18T01:00:00+00:00",),
        )
        repository.connection.commit()
        result = _exporter(root, repository).rebuild()

    assert result.resumed is False
    assert result.rows_processed == 3
    pointer_text = "\n".join(
        path.read_text(encoding="utf-8")
        for path in (root / "views").rglob("*.json")
        if path.name != "_mailvault_views.json"
    )
    assert "Changed subject" in pointer_text


def test_current_snapshot_is_a_no_op_until_source_changes(tmp_path: Path) -> None:
    root = tmp_path / "archive"
    database = root / "database" / "mailvault.sqlite3"

    with ArchiveRepository(database) as repository:
        _seed_view_source(repository)
        first = _exporter(root, repository).rebuild()
        marker = root / "views" / "_mailvault_views.json"
        first_marker = marker.read_bytes()
        second = _exporter(root, repository).rebuild()

    assert first.up_to_date is False
    assert second.up_to_date is True
    assert second.total_rows == first.total_rows
    assert second.total_pointers == first.total_pointers
    assert marker.read_bytes() == first_marker


def test_progress_reports_exact_rows_and_pointer_totals(tmp_path: Path) -> None:
    root = tmp_path / "archive"
    database = root / "database" / "mailvault.sqlite3"
    events: list[tuple[str, dict[str, object]]] = []

    with ArchiveRepository(database) as repository:
        _seed_view_source(repository, message_count=2)
        result = _exporter(root, repository).rebuild(
            progress=lambda event, payload: events.append((event, payload))
        )

    planned = next(payload for event, payload in events if event == "planned")
    completed = next(payload for event, payload in events if event == "completed")
    assert planned["total_rows"] == 2
    assert planned["total_pointers"] == 12
    assert completed["processed_rows"] == 2
    assert completed["pointers_written"] == 12
    assert result.counts == {
        "by-domain": 2,
        "by-label": 4,
        "by-mailbox": 2,
        "by-thread": 2,
        "by-year": 2,
    }
