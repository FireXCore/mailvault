# Getting started

## Requirements

- Python 3.12 or newer
- An IMAP-enabled mailbox
- A Gmail App Password for Gmail accounts, or the credentials required by a generic IMAP provider
- A destination volume with enough free space for raw EML, attachment blobs, SQLite, and derived exports

MailVault does not require a database server. SQLite is created inside the archive.

## Install from a source checkout

```bash
git clone https://github.com/FireXCore/mailvault.git
cd mailvault
python -m venv .venv
```

Windows PowerShell:

```powershell
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -e .
```

Linux/macOS:

```bash
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -e .
```

## Validate the installation

```bash
mailvault version
python -m firexcore_mailvault version
```

Both commands must report the same installed distribution version.

## Run the doctor command

The doctor command authenticates, validates TLS, reads server capabilities and lists archive roots. It does not download complete messages.

Gmail:

```powershell
mailvault doctor `
  --account user@gmail.com `
  --host imap.gmail.com `
  --provider gmail `
  --auth app-password
```

Generic IMAP:

```powershell
mailvault doctor `
  --account user@example.com `
  --host mail.example.com `
  --provider generic-imap `
  --auth password
```

## Run the first sync

For a complete evidence archive, use `--scope all`.

```powershell
mailvault sync `
  --account user@gmail.com `
  --host imap.gmail.com `
  --provider gmail `
  --auth app-password `
  --destination E:\MailVault `
  --scope all
```

The first phase discovers metadata. The second phase fetches pending raw messages. Stopping the process does not invalidate the archive; use the same destination and command to resume.

## Audit Gmail label coverage

For Gmail, full-scope sync performs remote label reconciliation before reporting `complete`. You can also rerun the audit explicitly before final verification:

```powershell
mailvault audit-labels `
  --account user@gmail.com `
  --host imap.gmail.com `
  --destination E:\MailVault
```

A passing audit proves that every Gmail message visible through those labels has a corresponding archived raw EML identity.

## Verify the archive

```powershell
mailvault verify --destination E:\MailVault
```

## Generate portable exports and navigation views

```powershell
mailvault export --destination E:\MailVault
mailvault views --destination E:\MailVault
```

<p align="center">
  <img src="assets/views-progress-terminal.png" alt="MailVault live view-build progress" width="100%">
</p>

`mailvault views` first plans an exact source snapshot and then displays determinate source-row progress, exact pointer writes, percentage, and ETA. After `Ctrl+C`, run the identical command to continue from the last durable source-row checkpoint.

```powershell
mailvault views --destination E:\MailVault
```

Use `--restart` only when you explicitly want to discard the incomplete staging build:

```powershell
mailvault views --destination E:\MailVault --restart
```

A successful result reports `REBUILT` or `RESUMED`. A second run against an unchanged archive reports `UP TO DATE` without rewriting pointers. See [Resumable navigation views](RESUMABLE_VIEWS.md).

## Recommended first-run sequence

1. Run `doctor`.
2. Run a narrow date or query scope against a new destination when validating a new provider.
3. Inspect `reports`, `logs`, `metadata/messages`, and `manifests`.
4. Start the full `scope=all` archive.
5. For Gmail, run `audit-labels` and require a passing result.
6. Run `verify`.
7. Preserve the destination and resume rather than restarting from an empty directory.
