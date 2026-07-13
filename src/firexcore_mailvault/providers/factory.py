from __future__ import annotations

from firexcore_mailvault.models import ProviderKind, ServerCapabilities
from firexcore_mailvault.providers.base import ProviderProfile
from firexcore_mailvault.providers.generic import GenericImapProfile
from firexcore_mailvault.providers.gmail import GmailImapProfile


def resolve_provider(
    requested: ProviderKind,
    capabilities: ServerCapabilities,
) -> ProviderProfile:
    if requested is ProviderKind.GMAIL:
        profile: ProviderProfile = GmailImapProfile()
    elif requested is ProviderKind.GENERIC_IMAP:
        profile = GenericImapProfile()
    else:
        profile = GmailImapProfile() if capabilities.gmail_extensions else GenericImapProfile()
    profile.validate_capabilities(capabilities)
    return profile
