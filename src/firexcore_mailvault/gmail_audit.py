from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path

from firexcore_mailvault.atomic import atomic_write_json
from firexcore_mailvault.models import MailboxInfo
from firexcore_mailvault.protocols.imap import ImapGatewayProtocol
from firexcore_mailvault.repository import ArchiveRepository


@dataclass(frozen=True, slots=True)
class GmailLabelCoverage:
    mailbox: str
    flags: tuple[str, ...]
    remote_messages: int
    archived_raw_messages: int
    missing_raw_messages: int
    missing_gmail_message_ids: tuple[str, ...]

    @property
    def passed(self) -> bool:
        return self.missing_raw_messages == 0


@dataclass(frozen=True, slots=True)
class GmailLabelAuditReport:
    account: str
    generated_at: str
    local_raw_message_ids: int
    labels: tuple[GmailLabelCoverage, ...]

    @property
    def passed(self) -> bool:
        return all(item.passed for item in self.labels)

    @property
    def missing_raw_messages(self) -> int:
        return len(
            {gmail_id for label in self.labels for gmail_id in label.missing_gmail_message_ids}
        )

    def as_dict(self) -> dict[str, object]:
        return {
            "account": self.account,
            "generated_at": self.generated_at,
            "local_raw_message_ids": self.local_raw_message_ids,
            "passed": self.passed,
            "missing_raw_messages": self.missing_raw_messages,
            "labels": [
                {
                    **asdict(label),
                    "passed": label.passed,
                }
                for label in self.labels
            ],
        }


def audit_gmail_labels(
    gateway: ImapGatewayProtocol,
    repository: ArchiveRepository,
    *,
    account_id: int,
    account: str,
    batch_size: int = 500,
) -> GmailLabelAuditReport:
    local_raw_ids = repository.gmail_raw_message_ids(account_id)
    coverages: list[GmailLabelCoverage] = []

    for mailbox in _selectable_mailboxes(gateway.list_mailboxes()):
        gateway.select_readonly(mailbox.name)
        uids = sorted(set(gateway.search_uids(("imap", "ALL"))))
        remote_ids: set[str] = set()

        for index in range(0, len(uids), batch_size):
            batch = uids[index : index + batch_size]
            remote_ids.update(gateway.fetch_gmail_message_ids(batch).values())

        missing = tuple(sorted(remote_ids - local_raw_ids))
        coverages.append(
            GmailLabelCoverage(
                mailbox=mailbox.name,
                flags=mailbox.flags,
                remote_messages=len(remote_ids),
                archived_raw_messages=len(remote_ids & local_raw_ids),
                missing_raw_messages=len(missing),
                missing_gmail_message_ids=missing,
            )
        )

    return GmailLabelAuditReport(
        account=account,
        generated_at=datetime.now(UTC).isoformat(),
        local_raw_message_ids=len(local_raw_ids),
        labels=tuple(coverages),
    )


def write_gmail_label_audit(report: GmailLabelAuditReport, reports_dir: Path) -> Path:
    timestamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    path = reports_dir / f"gmail-label-audit-{timestamp}.json"
    atomic_write_json(path, report.as_dict())
    return path


def _selectable_mailboxes(mailboxes: list[MailboxInfo]) -> list[MailboxInfo]:
    return sorted(
        (mailbox for mailbox in mailboxes if mailbox.selectable),
        key=lambda item: item.name.casefold(),
    )
