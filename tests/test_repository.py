from datetime import UTC, datetime
from pathlib import Path

from firexcore_mailvault.config import MailVaultConfig
from firexcore_mailvault.metadata import parse_header_bytes
from firexcore_mailvault.models import (
    MailboxInfo,
    MetadataRecord,
    ProviderKind,
    ProviderMetadata,
)
from firexcore_mailvault.repository import ArchiveRepository


def test_provider_identity_reuses_canonical_message(tmp_path: Path) -> None:
    repository = ArchiveRepository(tmp_path / "mailvault.sqlite3")
    config = MailVaultConfig(
        account="user@gmail.com",
        destination=tmp_path,
        host="imap.gmail.com",
    )
    account_id = repository.get_or_create_account(config, ProviderKind.GMAIL)
    mailbox_id = repository.upsert_mailbox(
        account_id, MailboxInfo("[Gmail]/All Mail", "/", ("\\All",))
    )
    generation = repository.get_or_create_generation(mailbox_id, 100, 0, None)
    headers = parse_header_bytes(
        b"Message-ID: <same@example.com>\r\nFrom: a@example.com\r\nSubject: Test\r\n\r\n"
    )

    ids = []
    for uid in (1, 2):
        record = MetadataRecord(
            uid=uid,
            flags=(),
            internal_date=datetime.now(UTC),
            rfc822_size=100,
            header_bytes=b"",
            modseq=None,
            provider=ProviderMetadata("999", "77", ("\\Inbox",), None, None),
        )
        message_id, _ = repository.upsert_metadata(
            account_id,
            generation.generation_id,
            record,
            headers,
            ("gmail-x-gm-msgid", "999"),
            ("gmail-x-gm-thrid", "77"),
            selected_for_raw=True,
        )
        ids.append(message_id)

    assert ids[0] == ids[1]
    assert repository.stats(account_id)["messages"] == 1
    assert repository.stats(account_id)["occurrences"] == 2
    repository.close()


def test_scan_checkpoints_are_isolated_by_scope_and_query(tmp_path: Path) -> None:
    with ArchiveRepository(tmp_path / "mailvault.sqlite3") as repository:
        config = MailVaultConfig(
            account="buyer@example.org",
            destination=tmp_path,
            host="imap.example.org",
        )
        account_id = repository.get_or_create_account(config, ProviderKind.GENERIC_IMAP)
        mailbox_id = repository.upsert_mailbox(account_id, MailboxInfo("INBOX", "/", ("\\Inbox",)))
        generation = repository.get_or_create_generation(mailbox_id, 100, 0, None)

        assert repository.get_or_create_scan_checkpoint(
            generation.generation_id, "generic-imap:all:"
        ) == (0, None)
        repository.update_scan_checkpoint(
            generation.generation_id,
            "generic-imap:all:",
            highest_uid=500,
            highest_modseq=20,
        )

        assert repository.get_or_create_scan_checkpoint(
            generation.generation_id, "generic-imap:all:"
        ) == (500, 20)
        assert repository.get_or_create_scan_checkpoint(
            generation.generation_id, "generic-imap:query:from:vendor@example.org"
        ) == (0, None)


def test_malformed_group_address_header_does_not_crash() -> None:
    headers = parse_header_bytes(
        b"Message-ID: <broken@example.com>\r\n"
        b"From: sender@example.com\r\n"
        b"To: Team: alpha@example.com, Broken Group: beta@example.com; ;\r\n"
        b"Subject: malformed address group\r\n\r\n"
    )

    addresses = {item.address for item in headers.to_values}
    assert "alpha@example.com" in addresses
    assert "beta@example.com" in addresses
