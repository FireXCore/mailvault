# CLI reference

## `mailvault version`

Print the installed package version. The value is read from Python distribution metadata.

## `mailvault doctor`

Validates connection prerequisites without archiving complete messages.

Important options:

```text
--account, -a       Complete email address
--host              IMAP hostname
--port              IMAP port; default 993
--provider          auto | gmail | generic-imap
--auth              app-password | password
--tls-mode          implicit | starttls
--timeout           Socket timeout in seconds
```

## `mailvault sync`

Creates or resumes an archive.

Important options:

```text
--config, -c        TOML configuration file
--account, -a       Complete email address
--destination, -d   Archive root
--host              IMAP hostname
--port              IMAP port
--provider          auto | gmail | generic-imap
--auth              app-password | password
--tls-mode          implicit | starttls
--scope             all | has-attachments | query
--query             Provider query used with scope=query
--include-spam      Include Spam/Junk archive roots
--include-trash     Include Trash archive roots
--mailbox           Repeatable mailbox pattern; Gmail labels are supported
--soft-cap          Rolling 24-hour soft download cap
--hard-cap          Rolling 24-hour hard download cap
--log-level         DEBUG | INFO | WARNING | ERROR
```

The value passed to `--auth` is the authentication mode, not the password itself.

Correct:

```text
--auth app-password
```

Incorrect:

```text
--auth <actual-secret>
```


## `mailvault audit-labels`

Performs a read-only Gmail reconciliation. It enumerates every IMAP-visible mailbox or label, retrieves `X-GM-MSGID` values, and compares them with locally archived raw EML identities.

```text
--account, -a       Gmail account present in the archive
--destination, -d   Archive root
--host              Gmail IMAP hostname; default imap.gmail.com
--port              IMAP port; default 993
--auth              app-password | password
--tls-mode          implicit | starttls
--timeout           Socket timeout in seconds
```

The command writes a timestamped JSON report under `reports/` and exits with code `2` when any remote Gmail message lacks raw EML. Full-scope Gmail sync performs the same audit automatically before reporting `complete`. The audit never downloads raw message bodies and does not mutate the mailbox.

## `mailvault stats`

```text
--destination, -d   Archive root
--account, -a       Optional account filter
```

## `mailvault verify`

```text
--destination, -d   Archive root
--sample            Fraction in the range 0.0001 to 1.0; default 1.0
```

A full verification recalculates every raw EML and blob hash.

## `mailvault export`

Regenerates portable JSONL manifests and `procurement_sources.jsonl` from SQLite.

## `mailvault views`

Builds disposable JSON pointer views by domain, sender, thread, mailbox, year, and label.

```powershell
mailvault views `
  --destination "E:\MailVault-E"
```

Options:

```text
--destination, -d    Archive root
--restart            Discard an incomplete staging build and start from row zero
```

The command performs four phases:

1. **Planning** scans the protected SQLite snapshot to calculate exact source-row and pointer totals and a deterministic fingerprint.
2. **Building** or **Resuming** writes pointers into `state/views-rebuild-staging-v3/`.
3. **Publishing** atomically replaces the completed `views/` snapshot.
4. **Completed** reports one of `REBUILT`, `RESUMED`, or `UP TO DATE`.

The progress display includes exact source rows, pointer writes, percentage, and ETA.

A safe interruption checkpoints fully completed source rows in:

```text
state/views-rebuild-v1.json
```

Rerun the same command to resume. Do not use `--restart` when the goal is to continue the existing staging build.

The previous completed `views/` tree remains available until the replacement is fully built and published. If SQLite changes after interruption, the stale checkpoint is rejected automatically. If the completed marker and source fingerprint already match, the command returns `UP TO DATE` without rewriting pointer files.

Completed snapshots contain:

```text
views/_mailvault_views.json
```

See [Resumable navigation views](RESUMABLE_VIEWS.md).

## Module execution

The package supports the module form:

```bash
python -m firexcore_mailvault version
python -m firexcore_mailvault sync --config config.toml
```
