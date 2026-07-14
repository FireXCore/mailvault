from __future__ import annotations

from pathlib import Path

from firexcore_mailvault.config import MailVaultConfig
from firexcore_mailvault.gmail_audit import audit_gmail_labels
from firexcore_mailvault.models import MailboxInfo
from firexcore_mailvault.paths import build_archive_paths
from firexcore_mailvault.protocols.imap.capabilities import parse_capabilities
from firexcore_mailvault.protocols.imap.gateway import SelectResult
from firexcore_mailvault.repository import ArchiveRepository


class AuditGateway:
    def __init__(self) -> None:
        self.capabilities = parse_capabilities([b"IMAP4rev1", b"X-GM-EXT-1"])
        self.selected_mailbox: str | None = None
        self._mailbox_uids = {
            "[Gmail]/All Mail": [1, 2],
            "Suppliers": [2, 3],
        }
        self._gmail_ids = {
            1: "1001",
            2: "1002",
            3: "1003",
        }

    def list_mailboxes(self) -> list[MailboxInfo]:
        return [
            MailboxInfo("[Gmail]/All Mail", "/", ("\\All",)),
            MailboxInfo("Suppliers", "/", ("\\HasNoChildren",)),
        ]

    def select_readonly(self, mailbox: str) -> SelectResult:
        self.selected_mailbox = mailbox
        return SelectResult(1, 3, None, None, len(self._mailbox_uids[mailbox]))

    def search_uids(self, description: object) -> list[int]:
        assert description == ("imap", "ALL")
        assert self.selected_mailbox is not None
        return self._mailbox_uids[self.selected_mailbox]

    def fetch_metadata(self, uids: list[int], extra_items: list[str]) -> list[object]:
        raise AssertionError("metadata fetch is not used by the label audit")

    def fetch_raw(self, uid: int) -> bytes:
        raise AssertionError("raw fetch is not used by the label audit")

    def fetch_gmail_message_ids(self, uids: list[int]) -> dict[int, str]:
        return {uid: self._gmail_ids[uid] for uid in uids}

    def reconnect(self) -> None:
        return None


def test_gmail_label_audit_reports_remote_messages_without_raw(tmp_path: Path) -> None:
    config = MailVaultConfig(
        account="buyer@gmail.com",
        destination=tmp_path / "archive",
        host="imap.gmail.com",
    )
    paths = build_archive_paths(config.destination)

    with ArchiveRepository(paths.database) as repository:
        account_id = repository.get_or_create_account(config, config.provider)
        now = "2026-01-01T00:00:00+00:00"
        with repository.transaction() as connection:
            for message_id, gmail_id in ((1, "1001"), (2, "1002")):
                connection.execute(
                    """
                    INSERT INTO messages(
                        id, archive_id, account_id, raw_path, raw_sha256,
                        raw_size_bytes, created_at, updated_at
                    ) VALUES(?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        message_id,
                        f"archive-{message_id}",
                        account_id,
                        f"objects/raw/{gmail_id}",
                        gmail_id.zfill(64),
                        10,
                        now,
                        now,
                    ),
                )
                connection.execute(
                    """
                    INSERT INTO message_identities(
                        account_id, message_id, namespace, value, created_at
                    ) VALUES(?, ?, 'gmail-x-gm-msgid', ?, ?)
                    """,
                    (account_id, message_id, gmail_id, now),
                )

        report = audit_gmail_labels(
            AuditGateway(),
            repository,
            account_id=account_id,
            account=config.account,
        )

    assert report.passed is False
    assert report.missing_raw_messages == 1
    suppliers = next(item for item in report.labels if item.mailbox == "Suppliers")
    assert suppliers.remote_messages == 2
    assert suppliers.archived_raw_messages == 1
    assert suppliers.missing_gmail_message_ids == ("1003",)
