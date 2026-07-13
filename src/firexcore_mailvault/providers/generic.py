from __future__ import annotations

import fnmatch
import shlex
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


class GenericImapProfile(ProviderProfile):
    kind = ProviderKind.GENERIC_IMAP
    display_name = "Generic IMAP"

    def validate_capabilities(self, capabilities: ServerCapabilities) -> None:
        if not any(value.casefold() in {"imap4rev1", "imap4rev2"} for value in capabilities.raw):
            raise ImapCapabilityError("The server does not advertise IMAP4rev1 or IMAP4rev2.")

    def choose_mailboxes(
        self,
        mailboxes: Sequence[MailboxInfo],
        *,
        include_spam: bool,
        include_trash: bool,
        patterns: Sequence[str],
    ) -> list[MailboxInfo]:
        selected: list[MailboxInfo] = []
        for mailbox in mailboxes:
            if not mailbox.selectable:
                continue
            flags = {flag.casefold() for flag in mailbox.flags}
            if not include_spam and ("\\junk" in flags or "\\spam" in flags):
                continue
            if not include_trash and "\\trash" in flags:
                continue
            if patterns and not any(
                fnmatch.fnmatchcase(mailbox.name, pattern) for pattern in patterns
            ):
                continue
            selected.append(mailbox)
        return selected

    def metadata_fetch_items(self, capabilities: ServerCapabilities) -> list[str]:
        items: list[str] = []
        if capabilities.object_id:
            items.extend(["EMAILID", "THREADID"])
        if capabilities.condstore:
            items.append("MODSEQ")
        return items

    def search_criteria(self, scope: ArchiveScope, query: str | None) -> object:
        if scope is ArchiveScope.ALL:
            return ["ALL"]
        if scope is ArchiveScope.HAS_ATTACHMENTS:
            # Generic IMAP has no portable HASATTACHMENT criterion. Search all messages;
            # attachment filtering occurs after MIME parsing so no data is silently lost.
            return ["ALL"]
        if not query:
            raise ValueError("query is required for query scope")
        # Query syntax is a JSON-free, shell-friendly sequence separated by spaces.
        # Quoted strings are handled by the CLI before reaching this profile.
        return shlex.split(query)

    def stable_message_identity(self, record: MetadataRecord) -> tuple[str, str] | None:
        if record.provider.email_object_id:
            return ("imap-objectid-emailid", record.provider.email_object_id)
        return None

    def stable_thread_identity(self, record: MetadataRecord) -> tuple[str, str] | None:
        if record.provider.thread_object_id:
            return ("imap-objectid-threadid", record.provider.thread_object_id)
        return None
