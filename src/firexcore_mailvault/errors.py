from __future__ import annotations


class MailVaultError(Exception):
    """Base application error."""


class ConfigurationError(MailVaultError):
    """Configuration is invalid."""


class AuthenticationError(MailVaultError):
    """Authentication failed."""


class ImapCapabilityError(MailVaultError):
    """The server lacks a capability required by the selected operation."""


class BandwidthLimitReached(MailVaultError):
    """The configured rolling bandwidth limit has been reached."""


class IntegrityError(MailVaultError):
    """Archive integrity verification failed."""


class ArchiveConflictError(MailVaultError):
    """Existing immutable content conflicts with incoming content."""


class UnsafeServerError(MailVaultError):
    """Server configuration would weaken transport security."""
