from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import StrEnum
from pathlib import Path
from typing import Any
from uuid import UUID


class ProviderKind(StrEnum):
    AUTO = "auto"
    GENERIC_IMAP = "generic-imap"
    GMAIL = "gmail"


class AuthKind(StrEnum):
    PASSWORD = "password"
    APP_PASSWORD = "app-password"


class TlsMode(StrEnum):
    IMPLICIT = "implicit"
    STARTTLS = "starttls"


class ArchiveScope(StrEnum):
    ALL = "all"
    HAS_ATTACHMENTS = "has-attachments"
    QUERY = "query"


class PartRole(StrEnum):
    BODY_PLAIN = "body_plain"
    BODY_HTML = "body_html"
    INLINE_RESOURCE = "inline_resource"
    ATTACHMENT = "attachment"
    SECURITY_ARTIFACT = "security_artifact"
    TNEF_CONTAINER = "tnef_container"
    NESTED_MESSAGE = "nested_message"
    ENCRYPTED_CONTAINER = "encrypted_container"
    UNKNOWN = "unknown"


class IdentityKind(StrEnum):
    GMAIL_MESSAGE_ID = "gmail_message_id"
    OBJECTID_EMAILID = "objectid_emailid"
    RFC_MESSAGE_ID = "rfc_message_id"
    RAW_SHA256 = "raw_sha256"


@dataclass(frozen=True, slots=True)
class AddressValue:
    name: str
    address: str
    domain: str | None

    def as_dict(self) -> dict[str, str | None]:
        return {"name": self.name, "address": self.address, "domain": self.domain}


@dataclass(frozen=True, slots=True)
class MailboxInfo:
    name: str
    delimiter: str | None
    flags: tuple[str, ...]

    @property
    def selectable(self) -> bool:
        folded = {flag.casefold() for flag in self.flags}
        return "\\noselect" not in folded

    def has_flag(self, flag: str) -> bool:
        wanted = flag.casefold()
        return any(value.casefold() == wanted for value in self.flags)


@dataclass(frozen=True, slots=True)
class SelectedMailbox:
    mailbox_id: int
    generation_id: int
    name: str
    uidvalidity: int
    highest_uid: int
    highest_modseq: int | None
    mailbox_object_id: str | None


@dataclass(frozen=True, slots=True)
class ServerCapabilities:
    raw: tuple[str, ...]
    imap4rev2: bool
    gmail_extensions: bool
    object_id: bool
    condstore: bool
    qresync: bool
    special_use: bool
    uidplus: bool
    idle: bool
    literal_plus: bool
    uid_only: bool
    message_limit: int | None
    save_limit: int | None

    def supports(self, name: str) -> bool:
        needle = name.casefold()
        return any(item.casefold() == needle for item in self.raw)


@dataclass(frozen=True, slots=True)
class ProviderMetadata:
    provider_message_id: str | None
    provider_thread_id: str | None
    labels: tuple[str, ...]
    email_object_id: str | None
    thread_object_id: str | None


@dataclass(frozen=True, slots=True)
class MetadataRecord:
    uid: int
    flags: tuple[str, ...]
    internal_date: datetime | None
    rfc822_size: int
    header_bytes: bytes
    modseq: int | None
    provider: ProviderMetadata


@dataclass(frozen=True, slots=True)
class ParsedHeaders:
    rfc_message_id: str | None
    in_reply_to: str | None
    references: tuple[str, ...]
    subject_raw: str
    subject_normalized: str
    from_values: tuple[AddressValue, ...]
    sender_values: tuple[AddressValue, ...]
    reply_to_values: tuple[AddressValue, ...]
    to_values: tuple[AddressValue, ...]
    cc_values: tuple[AddressValue, ...]
    bcc_values: tuple[AddressValue, ...]
    return_path: str | None
    delivered_to: tuple[str, ...]
    x_original_to: tuple[str, ...]
    list_id: str | None
    header_date: datetime | None
    content_type: str | None
    authentication_results: tuple[str, ...]
    received_headers: tuple[str, ...]
    all_headers: dict[str, list[str]]


@dataclass(slots=True)
class ParsedPart:
    part_path: str
    parent_part_path: str | None
    role: PartRole
    declared_mime_type: str
    detected_mime_type: str | None
    content_disposition: str | None
    content_id: str | None
    filename_original: str | None
    filename_safe: str | None
    charset: str | None
    transfer_encoding: str | None
    size_bytes: int
    sha256: str | None
    blob_path: str | None
    headers: dict[str, list[str]] = field(default_factory=dict)
    defects: list[str] = field(default_factory=list)


@dataclass(slots=True)
class ParsedMessage:
    plain_text: str | None
    html_text: str | None
    html_visible_text: str | None
    charsets: tuple[str, ...]
    parts: list[ParsedPart]
    defects: list[str]


@dataclass(frozen=True, slots=True)
class CanonicalMessageRef:
    id: int
    archive_id: UUID
    provider_message_id: str | None
    raw_sha256: str | None


@dataclass(frozen=True, slots=True)
class ArchivePaths:
    root: Path
    raw_objects: Path
    blobs: Path
    metadata_messages: Path
    database: Path
    manifests: Path
    state: Path
    reports: Path
    views: Path
    logs: Path


@dataclass(slots=True)
class SyncSummary:
    run_id: int
    status: str
    mailboxes_scanned: int = 0
    metadata_scanned: int = 0
    raw_archived: int = 0
    bytes_downloaded: int = 0
    errors: int = 0
    stop_reason: str | None = None


JsonValue = str | int | float | bool | None | list["JsonValue"] | dict[str, "JsonValue"]
JsonObject = dict[str, JsonValue]
AnyMapping = dict[str, Any]
