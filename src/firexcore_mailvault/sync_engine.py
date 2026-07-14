from __future__ import annotations

import logging
from collections.abc import Callable, Iterable, Sequence
from dataclasses import dataclass
from functools import partial
from typing import TypeVar

from firexcore_mailvault.archive import BlobStore, ContentAddressedStore
from firexcore_mailvault.atomic import atomic_write_json
from firexcore_mailvault.config import MailVaultConfig
from firexcore_mailvault.errors import AuthenticationError, BandwidthLimitReached
from firexcore_mailvault.gmail_audit import audit_gmail_labels, write_gmail_label_audit
from firexcore_mailvault.metadata import parse_header_bytes
from firexcore_mailvault.mime_parser import parse_message
from firexcore_mailvault.models import ArchivePaths, ArchiveScope, ProviderKind, SyncSummary
from firexcore_mailvault.protocols.imap import ImapGatewayProtocol, effective_batch_size
from firexcore_mailvault.providers.base import ProviderProfile
from firexcore_mailvault.repository import ArchiveRepository
from firexcore_mailvault.retry import RetryPolicy
from firexcore_mailvault.throttling import BandwidthThrottle, ThrottleSettings

LOGGER = logging.getLogger(__name__)
_SEARCH_PLAN_VERSION = 2
ProgressCallback = Callable[[str, dict[str, object]], None]
T = TypeVar("T")


@dataclass(frozen=True, slots=True)
class SyncContext:
    account_id: int
    run_id: int


class SyncEngine:
    def __init__(
        self,
        config: MailVaultConfig,
        paths: ArchivePaths,
        repository: ArchiveRepository,
        gateway: ImapGatewayProtocol,
        profile: ProviderProfile,
        *,
        progress: ProgressCallback | None = None,
    ) -> None:
        self.config = config
        self.paths = paths
        self.repository = repository
        self.gateway = gateway
        self.profile = profile
        self.progress = progress or (lambda _event, _payload: None)
        self.raw_store = ContentAddressedStore(paths.raw_objects, paths.root)
        self.blob_store = BlobStore(paths.blobs, paths.root)
        self.retry = RetryPolicy(config.max_retries)

    def run(self) -> SyncSummary:
        account_id = self.repository.get_or_create_account(self.config, self.profile.kind)
        self.repository.record_capabilities(account_id, self.gateway.capabilities)
        run_id = self.repository.start_run(
            account_id,
            self.config.scope.value,
            self.config.query,
        )
        context = SyncContext(account_id=account_id, run_id=run_id)
        summary = SyncSummary(run_id=run_id, status="running")
        try:
            self._discover_metadata(context, summary)
            self._archive_pending(context, summary)
            self._finalize_coverage(context, summary)
        except BandwidthLimitReached as exc:
            summary.status = "paused"
            summary.stop_reason = str(exc)
        except KeyboardInterrupt:
            summary.status = "interrupted"
            summary.stop_reason = "Interrupted by operator"
            raise
        except Exception as exc:
            summary.status = "failed"
            summary.stop_reason = str(exc)
            raise
        finally:
            self.repository.finish_run(
                run_id,
                status=summary.status,
                mailboxes_scanned=summary.mailboxes_scanned,
                metadata_scanned=summary.metadata_scanned,
                raw_archived=summary.raw_archived,
                bytes_downloaded=summary.bytes_downloaded,
                errors=summary.errors,
                stop_reason=summary.stop_reason,
            )
        return summary

    def _finalize_coverage(self, context: SyncContext, summary: SyncSummary) -> None:
        if self.profile.kind is not ProviderKind.GMAIL or self.config.scope is not ArchiveScope.ALL:
            summary.status = "complete"
            return

        report = audit_gmail_labels(
            self.gateway,
            self.repository,
            account_id=context.account_id,
            account=self.config.account,
        )
        report_path = write_gmail_label_audit(report, self.paths.reports)
        self.progress(
            "label_audit_complete",
            {
                "passed": report.passed,
                "missing_raw_messages": report.missing_raw_messages,
                "report": str(report_path),
            },
        )

        if report.passed:
            summary.status = "complete"
            return

        summary.status = "incomplete"
        summary.stop_reason = (
            "Gmail label coverage failed: "
            f"{report.missing_raw_messages} unique remote messages lack raw EML. "
            f"See {report_path}."
        )

    def _discover_metadata(self, context: SyncContext, summary: SyncSummary) -> None:
        available = self.gateway.list_mailboxes()
        selected = self.profile.choose_mailboxes(
            available,
            include_spam=self.config.include_spam,
            include_trash=self.config.include_trash,
            patterns=self.config.mailbox_patterns,
        )
        if not selected:
            raise RuntimeError("No selectable mailboxes matched the configured archive scope.")

        batch_size = effective_batch_size(
            self.config.metadata_batch_size,
            self.gateway.capabilities,
        )
        search_description = self.profile.search_criteria(self.config.scope, self.config.query)
        extra_items = self.profile.metadata_fetch_items(self.gateway.capabilities)
        selection_key = self._selection_key()

        for mailbox in selected:
            select_result = self._retry_operation(
                partial(self.gateway.select_readonly, mailbox.name),
                stage=f"select:{mailbox.name}",
            )
            mailbox_id = self.repository.upsert_mailbox(
                context.account_id,
                mailbox,
                mailbox_object_id=select_result.mailbox_object_id,
            )
            generation = self.repository.get_or_create_generation(
                mailbox_id,
                select_result.uidvalidity,
                select_result.highest_uid,
                select_result.highest_modseq,
            )
            checkpoint_uid, checkpoint_modseq = self.repository.get_or_create_scan_checkpoint(
                generation.generation_id,
                selection_key,
            )
            found_uids = self._retry_operation(
                partial(self.gateway.search_uids, search_description),
                stage=f"search:{mailbox.name}",
            )
            # Arbitrary query results can change for old UIDs when labels/flags change.
            # Re-scan matching metadata for query scope; canonical identities and
            # occurrence upserts keep this idempotent. Fixed scopes resume by UID.
            if self.config.scope.value == "query":
                start_uid = 1
            else:
                start_uid = max(1, checkpoint_uid - self.config.overlap_uids + 1)
            uids = [uid for uid in sorted(set(found_uids)) if uid >= start_uid]
            highest_seen = checkpoint_uid
            highest_modseq = checkpoint_modseq

            for batch in _chunks(uids, batch_size):
                records = self._retry_operation(
                    partial(self.gateway.fetch_metadata, batch, extra_items),
                    stage=f"metadata:{mailbox.name}",
                )
                for record in records:
                    headers = parse_header_bytes(record.header_bytes)
                    stable_identity = self.profile.stable_message_identity(record)
                    thread_identity = self.profile.stable_thread_identity(record)
                    self.repository.upsert_metadata(
                        context.account_id,
                        generation.generation_id,
                        record,
                        headers,
                        stable_identity,
                        thread_identity,
                        selected_for_raw=True,
                    )
                    highest_seen = max(highest_seen, record.uid)
                    if record.modseq is not None:
                        highest_modseq = max(highest_modseq or 0, record.modseq)
                summary.metadata_scanned += len(records)
                self.repository.update_scan_checkpoint(
                    generation.generation_id,
                    selection_key,
                    highest_uid=highest_seen,
                    highest_modseq=highest_modseq,
                )
                self.progress(
                    "metadata_batch",
                    {
                        "mailbox": mailbox.name,
                        "batch": len(records),
                        "metadata_scanned": summary.metadata_scanned,
                    },
                )
            # Record a successful selection scan even when no new UIDs were returned.
            self.repository.update_scan_checkpoint(
                generation.generation_id,
                selection_key,
                highest_uid=max(highest_seen, max(found_uids, default=0)),
                highest_modseq=select_result.highest_modseq or highest_modseq,
            )
            # Mailbox generation tracks server-level observations, not query progress.
            self.repository.update_generation_checkpoint(
                generation.generation_id,
                highest_uid=select_result.highest_uid,
                highest_modseq=select_result.highest_modseq,
            )
            summary.mailboxes_scanned += 1
            self.progress(
                "mailbox_complete",
                {"mailbox": mailbox.name, "mailboxes_scanned": summary.mailboxes_scanned},
            )

    def _selection_key(self) -> str:
        query = self.config.query or ""
        return (
            f"v{_SEARCH_PLAN_VERSION}:{self.profile.kind.value}:{self.config.scope.value}:{query}"
        )

    def _archive_pending(self, context: SyncContext, summary: SyncSummary) -> None:
        throttle = BandwidthThrottle(
            self.repository,
            context.account_id,
            context.run_id,
            ThrottleSettings(
                delay_min_ms=self.config.raw_delay_min_ms,
                delay_max_ms=self.config.raw_delay_max_ms,
                pause_every_messages=self.config.pause_every_messages,
                pause_min_seconds=self.config.pause_min_seconds,
                pause_max_seconds=self.config.pause_max_seconds,
                soft_cap_bytes=self.config.soft_rolling_24h_cap_bytes,
                hard_cap_bytes=self.config.hard_rolling_24h_cap_bytes,
            ),
        )
        pending = self.repository.pending_raw_occurrences(context.account_id)
        self.progress("selection_complete", {"selected_messages": len(pending)})
        selected_mailbox: str | None = None
        consecutive_errors = 0

        for row in pending:
            occurrence_id = int(row["occurrence_id"])
            message_id = int(row["message_id"])
            mailbox_name = str(row["mailbox_name"])
            uid = int(row["uid"])
            expected_size = int(row["rfc822_size"] or 0)
            throttle.assert_can_fetch(expected_size)
            try:
                if selected_mailbox != mailbox_name:
                    self._retry_operation(
                        partial(self.gateway.select_readonly, mailbox_name),
                        stage=f"reselect:{mailbox_name}",
                    )
                    selected_mailbox = mailbox_name
                raw = self._retry_operation(
                    partial(self.gateway.fetch_raw, uid),
                    stage=f"raw:{mailbox_name}:{uid}",
                )
                stored_raw = self.raw_store.store(raw)
                canonical_id = self.repository.attach_raw_and_maybe_merge(
                    message_id,
                    raw_path=stored_raw.relative_path,
                    raw_sha256=stored_raw.sha256,
                    raw_size=stored_raw.size_bytes,
                )
                parsed = parse_message(raw, self.blob_store)
                self.repository.save_parsed_message(
                    canonical_id,
                    parsed.parsed_message,
                    parsed.part_records,
                )
                throttle.record(len(raw), "raw-message")
                throttle.after_raw_fetch()
                summary.raw_archived += 1
                summary.bytes_downloaded += len(raw)
                consecutive_errors = 0
                if self.config.write_per_message_json:
                    try:
                        document = self.repository.message_document(canonical_id)
                        archive_id = str(document["message"]["archive_id"])
                        atomic_write_json(
                            self.paths.metadata_messages / f"{archive_id}.json",
                            document,
                        )
                    except Exception as export_error:
                        summary.errors += 1
                        self.repository.record_failure(
                            context.run_id,
                            occurrence_id,
                            "message-json-export",
                            export_error,
                        )
                        LOGGER.exception(
                            "Raw message archived but per-message JSON export failed",
                            extra={"canonical_message_id": canonical_id},
                        )
                self.progress(
                    "raw_archived",
                    {
                        "raw_archived": summary.raw_archived,
                        "bytes_downloaded": summary.bytes_downloaded,
                        "mailbox": mailbox_name,
                        "uid": uid,
                    },
                )
            except BandwidthLimitReached:
                raise
            except Exception as exc:
                consecutive_errors += 1
                summary.errors += 1
                self.repository.mark_fetch_error(occurrence_id, str(exc))
                self.repository.record_failure(context.run_id, occurrence_id, "raw", exc)
                LOGGER.exception(
                    "Failed to archive message",
                    extra={"mailbox": mailbox_name, "uid": uid, "occurrence_id": occurrence_id},
                )
                if consecutive_errors >= self.config.max_consecutive_errors:
                    raise RuntimeError(
                        f"Stopped after {consecutive_errors} consecutive message failures."
                    ) from exc

    def _retry_operation(self, operation: Callable[[], T], *, stage: str) -> T:
        def on_retry(exc: BaseException, attempt: int, delay: float) -> None:
            LOGGER.warning(
                "Retrying IMAP operation",
                extra={
                    "stage": stage,
                    "attempt": attempt,
                    "delay_seconds": round(delay, 3),
                    "error_type": type(exc).__name__,
                    "error": str(exc),
                },
            )
            try:
                self.gateway.reconnect()
            except Exception:
                LOGGER.warning("Reconnect before retry failed", exc_info=True)

        return self.retry.run(
            operation,
            on_retry=on_retry,
            retryable=lambda exc: not isinstance(exc, AuthenticationError),
        )


def _chunks(values: Sequence[int], size: int) -> Iterable[list[int]]:
    for index in range(0, len(values), size):
        yield list(values[index : index + size])
