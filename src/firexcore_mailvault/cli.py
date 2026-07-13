from __future__ import annotations

import getpass
import os
from dataclasses import replace
from pathlib import Path
from typing import Annotated

import typer
from rich.console import Console
from rich.progress import Progress, SpinnerColumn, TextColumn
from rich.table import Table

from firexcore_mailvault import __version__
from firexcore_mailvault.config import MailVaultConfig, config_from_toml, parse_bytes
from firexcore_mailvault.errors import MailVaultError
from firexcore_mailvault.exporter import export_jsonl
from firexcore_mailvault.lock import RunLock
from firexcore_mailvault.logging_setup import configure_logging
from firexcore_mailvault.models import ArchiveScope, AuthKind, ProviderKind, SyncSummary, TlsMode
from firexcore_mailvault.paths import build_archive_paths
from firexcore_mailvault.procurement import ProcurementManifestExporter
from firexcore_mailvault.protocols.imap import ImapGateway
from firexcore_mailvault.providers import resolve_provider
from firexcore_mailvault.repository import ArchiveRepository
from firexcore_mailvault.sync_engine import SyncEngine
from firexcore_mailvault.unicode_safety import sanitize_text
from firexcore_mailvault.verifier import IntegrityVerifier
from firexcore_mailvault.view_exporter import ViewExporter

app = typer.Typer(
    name="mailvault",
    no_args_is_help=True,
    add_completion=False,
    help="Provider-neutral, read-only, evidence-preserving email archival.",
)
console = Console()


@app.command()
def version() -> None:
    """Print the installed version."""
    console.print(__version__)


@app.command()
def doctor(
    account: Annotated[str, typer.Option("--account", "-a", prompt=True)],
    host: Annotated[str, typer.Option("--host", prompt=True)],
    port: Annotated[int, typer.Option("--port")] = 993,
    provider: Annotated[ProviderKind, typer.Option("--provider")] = ProviderKind.AUTO,
    auth: Annotated[AuthKind, typer.Option("--auth")] = AuthKind.APP_PASSWORD,
    tls_mode: Annotated[TlsMode, typer.Option("--tls-mode")] = TlsMode.IMPLICIT,
    timeout: Annotated[int, typer.Option("--timeout")] = 90,
) -> None:
    """Verify authentication, TLS, capabilities, provider detection, and mailbox discovery."""
    secret = _secret(auth)
    try:
        with ImapGateway(
            account,
            secret,
            host=host,
            port=port,
            tls_mode=tls_mode,
            timeout_seconds=timeout,
            client_contact="https://github.com/FireXCore/mailvault/issues",
        ) as gateway:
            profile = resolve_provider(provider, gateway.capabilities)
            mailboxes = gateway.list_mailboxes()
            chosen = profile.choose_mailboxes(
                mailboxes,
                include_spam=False,
                include_trash=False,
                patterns=(),
            )
            table = Table(title="FireXCore MailVault Doctor")
            table.add_column("Check")
            table.add_column("Result")
            table.add_row("TLS", f"{tls_mode.value} {host}:{port}")
            table.add_row("Authentication", "PASS")
            table.add_row("Provider profile", profile.display_name)
            table.add_row(
                "IMAP revision", "IMAP4rev2" if gateway.capabilities.imap4rev2 else "IMAP4rev1"
            )
            table.add_row("Gmail extensions", _yes_no(gateway.capabilities.gmail_extensions))
            table.add_row("OBJECTID", _yes_no(gateway.capabilities.object_id))
            table.add_row("CONDSTORE", _yes_no(gateway.capabilities.condstore))
            table.add_row("QRESYNC", _yes_no(gateway.capabilities.qresync))
            table.add_row("UIDONLY", _yes_no(gateway.capabilities.uid_only))
            table.add_row(
                "MESSAGELIMIT",
                str(gateway.capabilities.message_limit)
                if gateway.capabilities.message_limit is not None
                else "not advertised",
            )
            table.add_row(
                "Selectable mailboxes", str(sum(1 for value in mailboxes if value.selectable))
            )
            table.add_row("Default archive roots", ", ".join(value.name for value in chosen))
            console.print(table)
    except Exception as exc:
        console.print(f"[red]Doctor failed:[/red] {sanitize_text(str(exc))}")
        raise typer.Exit(1) from exc


@app.command()
def sync(
    config: Annotated[Path | None, typer.Option("--config", "-c")] = None,
    account: Annotated[str | None, typer.Option("--account", "-a")] = None,
    destination: Annotated[Path | None, typer.Option("--destination", "-d")] = None,
    host: Annotated[str | None, typer.Option("--host")] = None,
    port: Annotated[int | None, typer.Option("--port")] = None,
    provider: Annotated[ProviderKind | None, typer.Option("--provider")] = None,
    auth: Annotated[AuthKind | None, typer.Option("--auth")] = None,
    tls_mode: Annotated[TlsMode | None, typer.Option("--tls-mode")] = None,
    scope: Annotated[ArchiveScope | None, typer.Option("--scope")] = None,
    query: Annotated[str | None, typer.Option("--query")] = None,
    include_spam: Annotated[bool | None, typer.Option("--include-spam/--exclude-spam")] = None,
    include_trash: Annotated[bool | None, typer.Option("--include-trash/--exclude-trash")] = None,
    mailbox: Annotated[list[str] | None, typer.Option("--mailbox")] = None,
    soft_cap: Annotated[str | None, typer.Option("--soft-cap")] = None,
    hard_cap: Annotated[str | None, typer.Option("--hard-cap")] = None,
    log_level: Annotated[str, typer.Option("--log-level")] = "INFO",
) -> None:
    """Archive complete messages and MIME provenance using a read-only IMAP session."""
    cfg = _resolve_config(
        config=config,
        account=account,
        destination=destination,
        host=host,
        port=port,
        provider=provider,
        auth=auth,
        tls_mode=tls_mode,
        scope=scope,
        query=query,
        include_spam=include_spam,
        include_trash=include_trash,
        mailbox=mailbox,
        soft_cap=soft_cap,
        hard_cap=hard_cap,
    )
    paths = build_archive_paths(cfg.destination)
    configure_logging(paths.logs / "mailvault.jsonl", log_level)
    secret = _secret(cfg.auth)
    progress_state: dict[str, int] = {"mailboxes": 0, "metadata": 0, "raw": 0}

    with Progress(
        SpinnerColumn(),
        TextColumn("{task.description}"),
        console=console,
        transient=False,
    ) as progress:
        task_id = progress.add_task("Connecting…", total=None)

        def on_progress(event: str, payload: dict[str, object]) -> None:
            if event == "metadata_batch":
                progress_state["metadata"] = _payload_int(payload, "metadata_scanned")
            elif event == "mailbox_complete":
                progress_state["mailboxes"] = _payload_int(payload, "mailboxes_scanned")
            elif event == "raw_archived":
                progress_state["raw"] = _payload_int(payload, "raw_archived")
            progress.update(
                task_id,
                description=(
                    f"Mailboxes {progress_state['mailboxes']} | "
                    f"Metadata {progress_state['metadata']} | Raw {progress_state['raw']}"
                ),
            )

        try:
            with (
                RunLock(paths.state / "sync.lock"),
                ArchiveRepository(paths.database) as repository,
                ImapGateway(
                    cfg.account,
                    secret,
                    host=cfg.host,
                    port=cfg.port,
                    tls_mode=cfg.tls_mode,
                    timeout_seconds=cfg.socket_timeout_seconds,
                    client_contact=cfg.client_contact,
                ) as gateway,
            ):
                profile = resolve_provider(cfg.provider, gateway.capabilities)
                summary = SyncEngine(
                    cfg,
                    paths,
                    repository,
                    gateway,
                    profile,
                    progress=on_progress,
                ).run()
                if cfg.write_jsonl_exports:
                    export_jsonl(repository, paths.manifests)
                    ProcurementManifestExporter(repository).export(
                        paths.manifests / "procurement_sources.jsonl"
                    )
            _print_sync_summary(summary)
        except KeyboardInterrupt as exc:
            console.print(
                "[yellow]Sync interrupted safely. Run the same command to resume.[/yellow]"
            )
            raise typer.Exit(130) from exc
        except (MailVaultError, OSError, ValueError, RuntimeError) as exc:
            console.print(f"[red]Sync failed:[/red] {sanitize_text(str(exc))}")
            raise typer.Exit(1) from exc


@app.command("stats")
def stats_command(
    destination: Annotated[Path, typer.Option("--destination", "-d")],
    account: Annotated[str | None, typer.Option("--account", "-a")] = None,
) -> None:
    """Show archive statistics."""
    paths = build_archive_paths(destination)
    with ArchiveRepository(paths.database) as repository:
        account_id = repository.find_account_id(account) if account else None
        if account and account_id is None:
            raise typer.BadParameter("Account does not exist in this archive.")
        values = repository.stats(account_id)
    table = Table(title="MailVault Statistics")
    table.add_column("Metric")
    table.add_column("Value", justify="right")
    for key, value in values.items():
        table.add_row(key.replace("_", " ").title(), f"{value:,}")
    console.print(table)


@app.command()
def verify(
    destination: Annotated[Path, typer.Option("--destination", "-d")],
    sample: Annotated[float, typer.Option("--sample", min=0.0001, max=1.0)] = 1.0,
) -> None:
    """Verify raw-message and attachment hashes."""
    paths = build_archive_paths(destination)
    with ArchiveRepository(paths.database) as repository:
        report = IntegrityVerifier(repository, paths.root).verify(sample)
    table = Table(title="Integrity Verification")
    table.add_column("Metric")
    table.add_column("Value", justify="right")
    table.add_row("Checked messages", str(report.checked_messages))
    table.add_row("Checked blobs", str(report.checked_blobs))
    table.add_row("Missing files", str(report.missing_files))
    table.add_row("Hash mismatches", str(report.hash_mismatches))
    table.add_row("Size mismatches", str(report.size_mismatches))
    table.add_row("Result", "PASS" if report.ok else "FAIL")
    console.print(table)
    if not report.ok:
        raise typer.Exit(2)


@app.command("export")
def export_command(
    destination: Annotated[Path, typer.Option("--destination", "-d")],
) -> None:
    """Regenerate portable JSONL manifests."""
    paths = build_archive_paths(destination)
    with ArchiveRepository(paths.database) as repository:
        outputs = export_jsonl(repository, paths.manifests)
        outputs.append(
            ProcurementManifestExporter(repository).export(
                paths.manifests / "procurement_sources.jsonl"
            )
        )
    for output in outputs:
        console.print(output)


@app.command("views")
def views_command(
    destination: Annotated[Path, typer.Option("--destination", "-d")],
) -> None:
    """Rebuild disposable domain, sender, thread, mailbox, year, and label views."""
    paths = build_archive_paths(destination)
    with ArchiveRepository(paths.database) as repository:
        counts = ViewExporter(repository, paths.root, paths.views).rebuild()
    table = Table(title="Views Rebuilt")
    table.add_column("View")
    table.add_column("Pointers", justify="right")
    for key, value in sorted(counts.items()):
        table.add_row(key, str(value))
    console.print(table)


def _resolve_config(
    *,
    config: Path | None,
    account: str | None,
    destination: Path | None,
    host: str | None,
    port: int | None,
    provider: ProviderKind | None,
    auth: AuthKind | None,
    tls_mode: TlsMode | None,
    scope: ArchiveScope | None,
    query: str | None,
    include_spam: bool | None,
    include_trash: bool | None,
    mailbox: list[str] | None,
    soft_cap: str | None,
    hard_cap: str | None,
) -> MailVaultConfig:
    if config:
        cfg = config_from_toml(config)
    else:
        resolved_account = account or typer.prompt("Email address")
        resolved_host = host or typer.prompt("IMAP host", default=_default_host(resolved_account))
        resolved_destination = destination or Path(typer.prompt("Archive destination"))
        cfg = MailVaultConfig(
            account=resolved_account,
            destination=resolved_destination,
            host=resolved_host,
        )
    cfg = replace(
        cfg,
        account=account or cfg.account,
        destination=destination or cfg.destination,
        host=host or cfg.host,
        port=port or cfg.port,
        provider=provider or cfg.provider,
        auth=auth or cfg.auth,
        tls_mode=tls_mode or cfg.tls_mode,
        scope=scope or cfg.scope,
        query=query if query is not None else cfg.query,
        include_spam=include_spam if include_spam is not None else cfg.include_spam,
        include_trash=include_trash if include_trash is not None else cfg.include_trash,
        mailbox_patterns=tuple(mailbox) if mailbox else cfg.mailbox_patterns,
        soft_rolling_24h_cap_bytes=(
            parse_bytes(soft_cap) if soft_cap else cfg.soft_rolling_24h_cap_bytes
        ),
        hard_rolling_24h_cap_bytes=(
            parse_bytes(hard_cap) if hard_cap else cfg.hard_rolling_24h_cap_bytes
        ),
    )
    cfg.validate()
    return cfg


def _secret(auth: AuthKind) -> str:
    value = os.getenv("MAILVAULT_SECRET")
    if value:
        return value
    label = "App Password" if auth is AuthKind.APP_PASSWORD else "Password"
    return getpass.getpass(f"{label}: ")


def _default_host(account: str) -> str:
    domain = account.rsplit("@", 1)[-1].casefold()
    return "imap.gmail.com" if domain in {"gmail.com", "googlemail.com"} else f"imap.{domain}"


def _yes_no(value: bool) -> str:
    return "yes" if value else "no"


def _payload_int(payload: dict[str, object], key: str) -> int:
    value = payload.get(key, 0)
    return int(value) if isinstance(value, int | str) else 0


def _print_sync_summary(summary: SyncSummary) -> None:
    table = Table(title="MailVault Sync Result")
    table.add_column("Metric")
    table.add_column("Value", justify="right")
    for label, attribute in (
        ("Run", "run_id"),
        ("Status", "status"),
        ("Mailboxes scanned", "mailboxes_scanned"),
        ("Metadata scanned", "metadata_scanned"),
        ("Raw EML archived", "raw_archived"),
        ("Downloaded bytes", "bytes_downloaded"),
        ("Errors", "errors"),
    ):
        value = getattr(summary, attribute)
        table.add_row(label, f"{value:,}" if isinstance(value, int) else str(value))
    stop_reason = summary.stop_reason
    if stop_reason:
        table.add_row("Stop reason", str(stop_reason))
    console.print(table)


def main() -> None:
    """Run the MailVault command-line application."""
    app()


if __name__ == "__main__":
    main()
