from __future__ import annotations

import re
import tomllib
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from firexcore_mailvault.errors import ConfigurationError
from firexcore_mailvault.models import ArchiveScope, AuthKind, ProviderKind, TlsMode

_BYTE_RE = re.compile(r"^\s*(\d+(?:\.\d+)?)\s*([kmgt]?i?b)?\s*$", re.IGNORECASE)


def parse_bytes(value: str | int) -> int:
    if isinstance(value, int):
        if value < 0:
            raise ConfigurationError("Byte count cannot be negative.")
        return value
    match = _BYTE_RE.match(value)
    if not match:
        raise ConfigurationError(f"Invalid byte quantity: {value!r}")
    number = float(match.group(1))
    unit = (match.group(2) or "b").lower()
    multipliers = {
        "b": 1,
        "kb": 1000,
        "mb": 1000**2,
        "gb": 1000**3,
        "tb": 1000**4,
        "kib": 1024,
        "mib": 1024**2,
        "gib": 1024**3,
        "tib": 1024**4,
    }
    return int(number * multipliers[unit])


@dataclass(frozen=True, slots=True)
class MailVaultConfig:
    account: str
    destination: Path
    host: str
    port: int = 993
    tls_mode: TlsMode = TlsMode.IMPLICIT
    provider: ProviderKind = ProviderKind.AUTO
    auth: AuthKind = AuthKind.APP_PASSWORD
    scope: ArchiveScope = ArchiveScope.ALL
    query: str | None = None
    include_spam: bool = False
    include_trash: bool = False
    mailbox_patterns: tuple[str, ...] = ()
    metadata_batch_size: int = 200
    overlap_uids: int = 200
    socket_timeout_seconds: int = 90
    raw_delay_min_ms: int = 250
    raw_delay_max_ms: int = 750
    pause_every_messages: int = 100
    pause_min_seconds: int = 5
    pause_max_seconds: int = 12
    soft_rolling_24h_cap_bytes: int = 1024**3
    hard_rolling_24h_cap_bytes: int = int(1.25 * 1024**3)
    max_retries: int = 5
    max_consecutive_errors: int = 5
    write_per_message_json: bool = True
    write_jsonl_exports: bool = True
    client_contact: str = "https://github.com/FireXCore/mailvault/issues"

    def validate(self) -> None:
        if "@" not in self.account:
            raise ConfigurationError("Account must be a complete email address.")
        if not self.host.strip():
            raise ConfigurationError("IMAP host is required.")
        if not 1 <= self.port <= 65535:
            raise ConfigurationError("IMAP port is invalid.")
        if self.tls_mode is TlsMode.IMPLICIT and self.port == 143:
            raise ConfigurationError("Implicit TLS should normally use port 993, not 143.")
        if self.tls_mode is TlsMode.STARTTLS and self.port == 993:
            raise ConfigurationError("STARTTLS should normally use port 143, not 993.")
        if not 10 <= self.metadata_batch_size <= 1000:
            raise ConfigurationError("metadata_batch_size must be between 10 and 1000.")
        if self.overlap_uids < 0:
            raise ConfigurationError("overlap_uids cannot be negative.")
        if self.raw_delay_min_ms < 0 or self.raw_delay_max_ms < self.raw_delay_min_ms:
            raise ConfigurationError("Invalid raw fetch delay range.")
        if self.pause_every_messages < 0:
            raise ConfigurationError("pause_every_messages cannot be negative.")
        if self.soft_rolling_24h_cap_bytes <= 0:
            raise ConfigurationError("Soft bandwidth cap must be positive.")
        if self.hard_rolling_24h_cap_bytes < self.soft_rolling_24h_cap_bytes:
            raise ConfigurationError("Hard bandwidth cap must be >= soft cap.")
        if self.max_retries < 1:
            raise ConfigurationError("max_retries must be at least 1.")
        if self.max_consecutive_errors < 1:
            raise ConfigurationError("max_consecutive_errors must be at least 1.")
        if self.scope is ArchiveScope.QUERY and not self.query:
            raise ConfigurationError("query is required when scope=query.")


def load_toml_config(path: Path) -> dict[str, Any]:
    with path.open("rb") as handle:
        return tomllib.load(handle)


def config_from_toml(path: Path) -> MailVaultConfig:
    raw = load_toml_config(path)
    account = raw.get("account", {})
    archive = raw.get("archive", {})
    imap = raw.get("imap", {})
    throttle = raw.get("throttle", {})
    output = raw.get("output", {})
    try:
        config = MailVaultConfig(
            account=str(account["email"]),
            destination=Path(str(archive["destination"])),
            host=str(imap["host"]),
            port=int(imap.get("port", 993)),
            tls_mode=TlsMode(str(imap.get("tls_mode", TlsMode.IMPLICIT.value))),
            provider=ProviderKind(str(account.get("provider", ProviderKind.AUTO.value))),
            auth=AuthKind(str(account.get("auth", AuthKind.APP_PASSWORD.value))),
            scope=ArchiveScope(str(archive.get("scope", ArchiveScope.ALL.value))),
            query=_optional_string(archive.get("query")),
            include_spam=bool(archive.get("include_spam", False)),
            include_trash=bool(archive.get("include_trash", False)),
            mailbox_patterns=tuple(str(v) for v in archive.get("mailbox_patterns", [])),
            metadata_batch_size=int(imap.get("metadata_batch_size", 200)),
            overlap_uids=int(imap.get("overlap_uids", 200)),
            socket_timeout_seconds=int(imap.get("socket_timeout_seconds", 90)),
            raw_delay_min_ms=int(throttle.get("raw_delay_min_ms", 250)),
            raw_delay_max_ms=int(throttle.get("raw_delay_max_ms", 750)),
            pause_every_messages=int(throttle.get("pause_every_messages", 100)),
            pause_min_seconds=int(throttle.get("pause_min_seconds", 5)),
            pause_max_seconds=int(throttle.get("pause_max_seconds", 12)),
            soft_rolling_24h_cap_bytes=parse_bytes(throttle.get("soft_rolling_24h_cap", "1GiB")),
            hard_rolling_24h_cap_bytes=parse_bytes(throttle.get("hard_rolling_24h_cap", "1.25GiB")),
            max_retries=int(throttle.get("max_retries", 5)),
            max_consecutive_errors=int(throttle.get("max_consecutive_errors", 5)),
            write_per_message_json=bool(output.get("write_per_message_json", True)),
            write_jsonl_exports=bool(output.get("write_jsonl_exports", True)),
            client_contact=str(
                imap.get("client_contact", "https://github.com/FireXCore/mailvault/issues")
            ),
        )
    except (KeyError, TypeError, ValueError) as exc:
        raise ConfigurationError(f"Invalid TOML configuration: {exc}") from exc
    config.validate()
    return config


def _optional_string(value: object) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None
