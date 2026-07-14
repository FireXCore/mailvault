from __future__ import annotations

import logging
import re
import ssl
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Protocol, cast

from imapclient import IMAPClient
from imapclient.exceptions import LoginError

from firexcore_mailvault import __version__
from firexcore_mailvault.errors import AuthenticationError, ImapCapabilityError
from firexcore_mailvault.models import (
    MailboxInfo,
    MetadataRecord,
    ProviderMetadata,
    ServerCapabilities,
    TlsMode,
)
from firexcore_mailvault.protocols.imap.capabilities import parse_capabilities
from firexcore_mailvault.unicode_safety import sanitize_text

LOGGER = logging.getLogger(__name__)

_HEADER_FIELDS = (
    "MESSAGE-ID IN-REPLY-TO REFERENCES DATE FROM SENDER REPLY-TO RETURN-PATH "
    "TO CC BCC SUBJECT DELIVERED-TO X-ORIGINAL-TO LIST-ID "
    "AUTHENTICATION-RESULTS ARC-AUTHENTICATION-RESULTS DKIM-SIGNATURE "
    "CONTENT-TYPE RECEIVED"
)
_BASE_METADATA_ITEMS = [
    "UID",
    "FLAGS",
    "INTERNALDATE",
    "RFC822.SIZE",
    f"BODY.PEEK[HEADER.FIELDS ({_HEADER_FIELDS})]",
]
_MESSAGE_LIMIT_RE = re.compile(r"MESSAGELIMIT(?:=|\s+)(\d+)", re.IGNORECASE)


@dataclass(frozen=True, slots=True)
class SelectResult:
    uidvalidity: int
    highest_uid: int
    highest_modseq: int | None
    mailbox_object_id: str | None
    exists: int


class ImapGatewayProtocol(Protocol):
    capabilities: ServerCapabilities
    selected_mailbox: str | None

    def list_mailboxes(self) -> list[MailboxInfo]: ...

    def select_readonly(self, mailbox: str) -> SelectResult: ...

    def search_uids(self, description: object) -> list[int]: ...

    def fetch_metadata(
        self,
        uids: Sequence[int],
        extra_items: Sequence[str],
    ) -> list[MetadataRecord]: ...

    def fetch_raw(self, uid: int) -> bytes: ...

    def fetch_gmail_message_ids(self, uids: Sequence[int]) -> dict[int, str]: ...

    def reconnect(self) -> None: ...


class ImapGateway:
    def __init__(
        self,
        account: str,
        secret: str,
        *,
        host: str,
        port: int,
        tls_mode: TlsMode,
        timeout_seconds: int,
        client_contact: str,
    ) -> None:
        self.account = account
        self._secret = secret
        self.host = host
        self.port = port
        self.tls_mode = tls_mode
        self.timeout_seconds = timeout_seconds
        self.client_contact = client_contact
        self.client: IMAPClient | None = None
        self.selected_mailbox: str | None = None
        self.capabilities = parse_capabilities(())

    def connect(self) -> None:
        context = ssl.create_default_context()
        context.minimum_version = ssl.TLSVersion.TLSv1_2
        use_ssl = self.tls_mode is TlsMode.IMPLICIT
        client = IMAPClient(
            self.host,
            port=self.port,
            ssl=use_ssl,
            ssl_context=context if use_ssl else None,
            timeout=self.timeout_seconds,
            use_uid=True,
        )
        try:
            if self.tls_mode is TlsMode.STARTTLS:
                client.starttls(ssl_context=context)
            client.login(self.account, self._secret)
        except LoginError as exc:
            client.shutdown()
            raise AuthenticationError(
                "IMAP authentication failed. Verify the username, password/app password, and server policy."
            ) from exc
        try:
            client.id_(
                {
                    "name": "firexcore-mailvault",
                    "version": __version__,
                    "vendor": "FireXCore",
                    "contact": self.client_contact,
                }
            )
        except Exception:
            LOGGER.debug("Server ID command was unavailable", exc_info=True)
        self.client = client
        self.selected_mailbox = None
        self.capabilities = parse_capabilities(client.capabilities())
        if not any(
            value.casefold() in {"imap4rev1", "imap4rev2"} for value in self.capabilities.raw
        ):
            raise ImapCapabilityError("The server does not advertise IMAP4rev1 or IMAP4rev2.")

    def close(self) -> None:
        if self.client is None:
            return
        try:
            self.client.logout()
        except Exception:
            LOGGER.debug("IMAP logout failed", exc_info=True)
            try:
                self.client.shutdown()
            except Exception:
                LOGGER.debug("IMAP shutdown failed", exc_info=True)
        finally:
            self.client = None
            self.selected_mailbox = None

    def reconnect(self) -> None:
        mailbox = self.selected_mailbox
        self.close()
        self.connect()
        if mailbox:
            self.select_readonly(mailbox)

    def __enter__(self) -> ImapGateway:
        self.connect()
        return self

    def __exit__(self, exc_type: object, exc: object, tb: object) -> None:
        self.close()

    def list_mailboxes(self) -> list[MailboxInfo]:
        client = self._require_client()
        result: list[MailboxInfo] = []
        for flags, delimiter, name in client.list_folders():
            result.append(
                MailboxInfo(
                    name=sanitize_text(str(name)),
                    delimiter=_optional_text(delimiter),
                    flags=tuple(sorted(_text(value) for value in flags)),
                )
            )
        return result

    def select_readonly(self, mailbox: str) -> SelectResult:
        client = self._require_client()
        response = client.select_folder(mailbox, readonly=True)
        self.selected_mailbox = mailbox
        uidvalidity = _response_int(response, b"UIDVALIDITY")
        if uidvalidity is None:
            raise ImapCapabilityError(f"Mailbox {mailbox!r} did not return UIDVALIDITY.")
        highest_uid = _response_int(response, b"UIDNEXT")
        highest_uid = max(0, (highest_uid or 1) - 1)
        highest_modseq = _response_int(response, b"HIGHESTMODSEQ")
        mailbox_object_id = _response_text(response, b"MAILBOXID")
        exists = _response_int(response, b"EXISTS") or 0
        return SelectResult(
            uidvalidity=uidvalidity,
            highest_uid=highest_uid,
            highest_modseq=highest_modseq,
            mailbox_object_id=mailbox_object_id,
            exists=exists,
        )

    def search_uids(self, description: object) -> list[int]:
        client = self._require_client()
        if isinstance(description, tuple) and len(description) == 2:
            strategy, value = description
            if strategy == "gmail":
                return [int(item) for item in client.gmail_search(str(value))]
            if strategy == "imap":
                return [int(item) for item in client.search([str(value)])]
        criteria = cast(Sequence[str | bytes], description)
        return [int(value) for value in client.search(criteria)]

    def fetch_metadata(
        self,
        uids: Sequence[int],
        extra_items: Sequence[str],
    ) -> list[MetadataRecord]:
        if not uids:
            return []
        client = self._require_client()
        items = [*_BASE_METADATA_ITEMS, *extra_items]
        response = client.fetch(list(uids), items)
        records: list[MetadataRecord] = []
        for uid in sorted(response):
            data = response[uid]
            header_bytes = _find_bytes(data, b"BODY[") or b""
            provider = ProviderMetadata(
                provider_message_id=_find_text(data, b"X-GM-MSGID"),
                provider_thread_id=_find_text(data, b"X-GM-THRID"),
                labels=_find_sequence_text(data, b"X-GM-LABELS"),
                email_object_id=_normalize_objectid(_find_text(data, b"EMAILID")),
                thread_object_id=_normalize_objectid(_find_text(data, b"THREADID")),
            )
            records.append(
                MetadataRecord(
                    uid=int(_find_scalar(data, b"UID") or uid),
                    flags=_find_sequence_text(data, b"FLAGS"),
                    internal_date=_find_datetime(data, b"INTERNALDATE"),
                    rfc822_size=int(_find_scalar(data, b"RFC822.SIZE") or 0),
                    header_bytes=header_bytes,
                    modseq=_find_modseq(data),
                    provider=provider,
                )
            )
        return records

    def fetch_raw(self, uid: int) -> bytes:
        client = self._require_client()
        response = client.fetch([uid], ["BODY.PEEK[]"])
        data = response.get(uid)
        if data is None:
            raise RuntimeError(f"Server returned no FETCH response for UID {uid}.")
        raw = _find_bytes(data, b"BODY[")
        if raw is None:
            raw = _find_bytes(data, b"RFC822")
        if raw is None:
            raise RuntimeError(f"Server returned no raw message bytes for UID {uid}.")
        return raw

    def fetch_gmail_message_ids(self, uids: Sequence[int]) -> dict[int, str]:
        if not uids:
            return {}
        client = self._require_client()
        response = client.fetch(list(uids), ["X-GM-MSGID"])
        result: dict[int, str] = {}
        for uid, data in response.items():
            value = _find_text(data, b"X-GM-MSGID")
            if value is not None:
                result[int(uid)] = value
        return result

    def noop(self) -> None:
        self._require_client().noop()

    def _require_client(self) -> IMAPClient:
        if self.client is None:
            raise RuntimeError("IMAP client is not connected")
        return self.client


def _find_key(data: dict[Any, Any], needle: bytes) -> Any | None:
    needle_upper = needle.upper()
    for key, value in data.items():
        key_bytes = key if isinstance(key, bytes) else str(key).encode("ascii", errors="ignore")
        if key_bytes.upper() == needle_upper:
            return value
    return None


def _find_prefixed(data: dict[Any, Any], prefix: bytes) -> Any | None:
    prefix_upper = prefix.upper()
    for key, value in data.items():
        key_bytes = key if isinstance(key, bytes) else str(key).encode("ascii", errors="ignore")
        if key_bytes.upper().startswith(prefix_upper):
            return value
    return None


def _find_scalar(data: dict[Any, Any], needle: bytes) -> Any | None:
    return _find_key(data, needle)


def _find_text(data: dict[Any, Any], needle: bytes) -> str | None:
    value = _find_key(data, needle)
    if value is None:
        return None
    if isinstance(value, (tuple, list)) and len(value) == 1:
        value = value[0]
    return _optional_text(value)


def _find_bytes(data: dict[Any, Any], prefix: bytes) -> bytes | None:
    value = _find_prefixed(data, prefix)
    if isinstance(value, bytes):
        return value
    return None


def _find_datetime(data: dict[Any, Any], needle: bytes) -> datetime | None:
    value = _find_key(data, needle)
    return value if isinstance(value, datetime) else None


def _find_sequence_text(data: dict[Any, Any], needle: bytes) -> tuple[str, ...]:
    value = _find_key(data, needle)
    if value is None:
        return ()
    if isinstance(value, (bytes, str)):
        return (_text(value),)
    if isinstance(value, Iterable):
        return tuple(sorted(_text(item) for item in value if _text(item)))
    return ()


def _find_modseq(data: dict[Any, Any]) -> int | None:
    value = _find_key(data, b"MODSEQ")
    if isinstance(value, int):
        return value
    if isinstance(value, (tuple, list)) and value:
        try:
            return int(value[0])
        except (TypeError, ValueError):
            return None
    return _coerce_int(value)


def _response_value(response: dict[Any, Any], key: bytes) -> Any | None:
    for candidate in (key, key.decode("ascii")):
        if candidate in response:
            return response[candidate]
    return None


def _response_int(response: dict[Any, Any], key: bytes) -> int | None:
    value = _response_value(response, key)
    if isinstance(value, (list, tuple)) and value:
        value = value[0]
    return _coerce_int(value)


def _response_text(response: dict[Any, Any], key: bytes) -> str | None:
    value = _response_value(response, key)
    if isinstance(value, (list, tuple)) and value:
        value = value[0]
    return _normalize_objectid(_optional_text(value))


def _coerce_int(value: object | None) -> int | None:
    if value is None:
        return None
    if isinstance(value, bool):
        return int(value)
    if isinstance(value, int):
        return value
    if isinstance(value, bytes):
        try:
            return int(value.decode("ascii"))
        except (UnicodeDecodeError, ValueError):
            return None
    if isinstance(value, str):
        try:
            return int(value)
        except ValueError:
            return None
    return None


def _normalize_objectid(value: str | None) -> str | None:
    if not value:
        return None
    text = value.strip()
    if text.startswith("(") and text.endswith(")"):
        text = text[1:-1].strip()
    return text or None


def _optional_text(value: object | None) -> str | None:
    if value is None:
        return None
    text = _text(value).strip()
    return text or None


def _text(value: object) -> str:
    if isinstance(value, bytes):
        return sanitize_text(value.decode("utf-8", errors="replace"))
    return sanitize_text(str(value))
