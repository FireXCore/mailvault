from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Sequence

from firexcore_mailvault.models import (
    ArchiveScope,
    MailboxInfo,
    MetadataRecord,
    ProviderKind,
    ServerCapabilities,
)


class ProviderProfile(ABC):
    kind: ProviderKind
    display_name: str

    @abstractmethod
    def validate_capabilities(self, capabilities: ServerCapabilities) -> None:
        """Raise when the server cannot support this provider profile."""

    @abstractmethod
    def choose_mailboxes(
        self,
        mailboxes: Sequence[MailboxInfo],
        *,
        include_spam: bool,
        include_trash: bool,
        patterns: Sequence[str],
    ) -> list[MailboxInfo]:
        """Choose mailbox roots to archive."""

    @abstractmethod
    def metadata_fetch_items(self, capabilities: ServerCapabilities) -> list[str]:
        """Return provider-specific FETCH data items."""

    @abstractmethod
    def search_criteria(self, scope: ArchiveScope, query: str | None) -> object:
        """Return a gateway-compatible search description."""

    @abstractmethod
    def stable_message_identity(self, record: MetadataRecord) -> tuple[str, str] | None:
        """Return identity namespace and value when the provider exposes one."""

    @abstractmethod
    def stable_thread_identity(self, record: MetadataRecord) -> tuple[str, str] | None:
        """Return thread identity namespace and value when available."""
