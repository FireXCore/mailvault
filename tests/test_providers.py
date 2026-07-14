from datetime import UTC, datetime

from firexcore_mailvault.models import (
    ArchiveScope,
    MailboxInfo,
    MetadataRecord,
    ProviderKind,
    ProviderMetadata,
)
from firexcore_mailvault.protocols.imap.capabilities import parse_capabilities
from firexcore_mailvault.providers import GmailImapProfile, resolve_provider


def test_auto_detects_gmail_and_uses_all_mail() -> None:
    caps = parse_capabilities([b"IMAP4rev1", b"X-GM-EXT-1"])
    profile = resolve_provider(ProviderKind.AUTO, caps)
    assert isinstance(profile, GmailImapProfile)

    chosen = profile.choose_mailboxes(
        [
            MailboxInfo("INBOX", "/", ("\\Inbox",)),
            MailboxInfo("[Gmail]/All Mail", "/", ("\\All",)),
            MailboxInfo("[Gmail]/Trash", "/", ("\\Trash",)),
        ],
        include_spam=False,
        include_trash=False,
        patterns=(),
    )
    assert [mailbox.name for mailbox in chosen] == ["[Gmail]/All Mail"]
    assert profile.search_criteria(ArchiveScope.ALL, None) == ("imap", "ALL")
    assert profile.search_criteria(ArchiveScope.HAS_ATTACHMENTS, None) == (
        "gmail",
        "has:attachment",
    )


def test_gmail_stable_identity() -> None:
    record = MetadataRecord(
        uid=1,
        flags=(),
        internal_date=datetime.now(UTC),
        rfc822_size=10,
        header_bytes=b"",
        modseq=None,
        provider=ProviderMetadata("123", "456", (), None, None),
    )
    profile = GmailImapProfile()
    assert profile.stable_message_identity(record) == ("gmail-x-gm-msgid", "123")
    assert profile.stable_thread_identity(record) == ("gmail-x-gm-thrid", "456")


def test_gmail_can_select_explicit_label_patterns() -> None:
    profile = GmailImapProfile()
    chosen = profile.choose_mailboxes(
        [
            MailboxInfo("[Gmail]/All Mail", "/", ("\\All",)),
            MailboxInfo("NIPHON", "/", ("\\HasNoChildren",)),
            MailboxInfo("Mr.Ayobi", "/", ("\\HasNoChildren",)),
        ],
        include_spam=False,
        include_trash=False,
        patterns=("NIP*",),
    )

    assert [mailbox.name for mailbox in chosen] == ["NIPHON"]
