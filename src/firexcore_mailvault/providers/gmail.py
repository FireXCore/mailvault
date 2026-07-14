from __future__ import annotations

import fnmatch
from collections.abc import Sequence

from firexcore_mailvault.errors import ImapCapabilityError
from firexcore_mailvault.models import (
    ArchiveScope,
    MailboxInfo,
    MetadataRecord,
    ProviderKind,
    ServerCapabilities,
)
from firexcore_mailvault.providers.base import ProviderProfile


class GmailImapProfile(ProviderProfile):
    kind = ProviderKind.GMAIL
    display_name = "Gmail IMAP"

    def validate_capabilities(self, capabilities: ServerCapabilities) -> None:
        if not capabilities.gmail_extensions:
            raise ImapCapabilityError("Gmail profile requires X-GM-EXT-1.")

    def choose_mailboxes(
        self,
        mailboxes: Sequence[MailboxInfo],
        *,
        include_spam: bool,
        include_trash: bool,
        patterns: Sequence[str],
    ) -> list[MailboxInfo]:
        if patterns:
            return [
                mailbox
                for mailbox in mailboxes
                if mailbox.selectable
                and any(fnmatch.fnmatchcase(mailbox.name, pattern) for pattern in patterns)
            ]

        all_mail = next((item for item in mailboxes if item.has_flag("\\All")), None)
        if all_mail is None:
            raise ImapCapabilityError(
                "Gmail All Mail could not be discovered via SPECIAL-USE flags."
            )
        selected = [all_mail]
        if include_spam:
            spam = next(
                (item for item in mailboxes if item.has_flag("\\Junk") or item.has_flag("\\Spam")),
                None,
            )
            if spam and spam.name != all_mail.name:
                selected.append(spam)
        if include_trash:
            trash = next((item for item in mailboxes if item.has_flag("\\Trash")), None)
            if trash and trash.name != all_mail.name:
                selected.append(trash)
        return selected

    def metadata_fetch_items(self, capabilities: ServerCapabilities) -> list[str]:
        items = ["X-GM-MSGID", "X-GM-THRID", "X-GM-LABELS"]
        if capabilities.condstore:
            items.append("MODSEQ")
        return items

    def search_criteria(self, scope: ArchiveScope, query: str | None) -> object:
        if scope is ArchiveScope.ALL:
            # Use the standard IMAP ALL search criterion. X-GM-RAW delegates to
            # Gmail web-search syntax, where the bare word "all" is a text query
            # rather than a universal match.
            return ("imap", "ALL")
        if scope is ArchiveScope.HAS_ATTACHMENTS:
            return ("gmail", "has:attachment")
        if not query:
            raise ValueError("query is required for query scope")
        return ("gmail", query)

    def stable_message_identity(self, record: MetadataRecord) -> tuple[str, str] | None:
        if record.provider.provider_message_id:
            return ("gmail-x-gm-msgid", record.provider.provider_message_id)
        return None

    def stable_thread_identity(self, record: MetadataRecord) -> tuple[str, str] | None:
        if record.provider.provider_thread_id:
            return ("gmail-x-gm-thrid", record.provider.provider_thread_id)
        return None
