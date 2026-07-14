from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

from firexcore_mailvault.config import MailVaultConfig
from firexcore_mailvault.models import (
    MailboxInfo,
    MetadataRecord,
    ProviderMetadata,
)
from firexcore_mailvault.paths import build_archive_paths
from firexcore_mailvault.protocols.imap.capabilities import parse_capabilities
from firexcore_mailvault.protocols.imap.gateway import SelectResult
from firexcore_mailvault.providers.generic import GenericImapProfile
from firexcore_mailvault.repository import ArchiveRepository
from firexcore_mailvault.sync_engine import SyncEngine


class FakeGateway:
    def __init__(self, raw: bytes) -> None:
        self.capabilities = parse_capabilities([b"IMAP4rev1", b"SPECIAL-USE"])
        self.selected_mailbox: str | None = None
        self.raw = raw

    def list_mailboxes(self) -> list[MailboxInfo]:
        return [MailboxInfo("INBOX", "/", ("\\Inbox",))]

    def select_readonly(self, mailbox: str) -> SelectResult:
        self.selected_mailbox = mailbox
        return SelectResult(1, 2, None, None, 2)

    def search_uids(self, description: object) -> list[int]:
        return [1, 2]

    def fetch_metadata(self, uids: list[int], extra_items: list[str]) -> list[MetadataRecord]:
        header = (
            b"Message-ID: <same@example.com>\r\n"
            b"From: Vendor <sales@vendor.example>\r\n"
            b"To: buyer@example.org\r\n"
            b"Subject: Quotation\r\n\r\n"
        )
        return [
            MetadataRecord(
                uid=uid,
                flags=("\\Seen",),
                internal_date=datetime(2020, 1, uid, tzinfo=UTC),
                rfc822_size=len(self.raw),
                header_bytes=header,
                modseq=None,
                provider=ProviderMetadata(None, None, (), None, None),
            )
            for uid in uids
        ]

    def fetch_raw(self, uid: int) -> bytes:
        return self.raw

    def fetch_gmail_message_ids(self, uids: list[int]) -> dict[int, str]:
        return {uid: str(uid) for uid in uids}

    def reconnect(self) -> None:
        return None


def test_sync_is_resumable_and_raw_hash_deduplicates_messages(
    sample_message_bytes: bytes,
    tmp_path: Path,
) -> None:
    config = MailVaultConfig(
        account="buyer@example.org",
        destination=tmp_path / "archive",
        host="imap.example.org",
        raw_delay_min_ms=0,
        raw_delay_max_ms=0,
        pause_every_messages=0,
        soft_rolling_24h_cap_bytes=10_000_000,
        hard_rolling_24h_cap_bytes=20_000_000,
    )
    paths = build_archive_paths(config.destination)
    with ArchiveRepository(paths.database) as repository:
        gateway = FakeGateway(sample_message_bytes)
        summary = SyncEngine(
            config,
            paths,
            repository,
            gateway,
            GenericImapProfile(),
        ).run()
        stats = repository.stats()

    assert summary.status == "complete"
    assert summary.raw_archived == 2
    assert stats["messages"] == 1
    assert stats["occurrences"] == 2
    assert stats["raw_messages"] == 1
    assert stats["blobs"] >= 2


class SurrogateMetadataGateway(FakeGateway):
    def fetch_metadata(self, uids: list[int], extra_items: list[str]) -> list[MetadataRecord]:
        records = super().fetch_metadata(uids, extra_items)
        return [
            MetadataRecord(
                uid=record.uid,
                flags=("\\Seen", "flag\udcff"),
                internal_date=record.internal_date,
                rfc822_size=record.rfc822_size,
                header_bytes=record.header_bytes,
                modseq=record.modseq,
                provider=ProviderMetadata(
                    None,
                    None,
                    ("Procurement\udce2\udc82\udcac", "Broken\ud800"),
                    None,
                    None,
                ),
            )
            for record in records
        ]


def test_sync_sanitizes_surrogate_metadata_without_losing_raw_message(
    sample_message_bytes: bytes,
    tmp_path: Path,
) -> None:
    config = MailVaultConfig(
        account="buyer@example.org",
        destination=tmp_path / "archive-surrogate",
        host="imap.example.org",
        raw_delay_min_ms=0,
        raw_delay_max_ms=0,
        pause_every_messages=0,
        soft_rolling_24h_cap_bytes=10_000_000,
        hard_rolling_24h_cap_bytes=20_000_000,
    )
    paths = build_archive_paths(config.destination)
    with ArchiveRepository(paths.database) as repository:
        gateway = SurrogateMetadataGateway(sample_message_bytes)
        summary = SyncEngine(
            config,
            paths,
            repository,
            gateway,
            GenericImapProfile(),
        ).run()
        occurrence = repository.connection.execute(
            "SELECT flags_json, labels_json FROM message_occurrences ORDER BY id LIMIT 1"
        ).fetchone()
        raw_row = repository.connection.execute(
            "SELECT raw_path FROM messages WHERE raw_path IS NOT NULL LIMIT 1"
        ).fetchone()

    assert summary.status == "complete"
    assert occurrence is not None
    assert "�" in str(occurrence["flags_json"])
    assert "Procurement€" in str(occurrence["labels_json"])
    assert raw_row is not None
    assert (paths.root / str(raw_row["raw_path"])).read_bytes() == sample_message_bytes
