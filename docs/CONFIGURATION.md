# Configuration

MailVault accepts command-line options or a TOML configuration file. Secrets are intentionally excluded from TOML.

## Complete example

```toml
[account]
email = "user@gmail.com"
provider = "gmail"          # auto | gmail | generic-imap
auth = "app-password"      # app-password | password

[imap]
host = "imap.gmail.com"
port = 993
tls_mode = "implicit"      # implicit | starttls
metadata_batch_size = 200
overlap_uids = 200
socket_timeout_seconds = 90
client_contact = "https://github.com/FireXCore/mailvault/issues"

[archive]
destination = "E:/MailVault"
scope = "all"              # all | has-attachments | query
query = ""
include_spam = false
include_trash = false
mailbox_patterns = []

[throttle]
raw_delay_min_ms = 250
raw_delay_max_ms = 750
pause_every_messages = 100
pause_min_seconds = 5
pause_max_seconds = 12
soft_rolling_24h_cap = "1GiB"
hard_rolling_24h_cap = "1.25GiB"
max_retries = 5
max_consecutive_errors = 5

[output]
write_per_message_json = true
write_jsonl_exports = true
```

## Provider selection

`auto` selects Gmail when Gmail extensions are advertised; otherwise it uses the generic IMAP profile. Explicit provider selection is recommended for reproducible operations.

## Archive scope

| Scope | Behavior |
|---|---|
| `all` | Archive all messages in selected archive roots. Required for complete procurement correspondence. |
| `has-attachments` | Archive messages selected by attachment-aware provider search. Body-only commercial decisions may be omitted. |
| `query` | Archive a provider query supplied through `query`. |

## Mailbox selection

Gmail uses the mailbox advertised with the `\All` Special-Use flag. Spam and Trash are excluded unless enabled.

Generic IMAP scans selectable mailboxes, optionally restricted through `mailbox_patterns`.

## Credentials

Interactive use prompts through hidden terminal input.

For controlled automation, set a process-scoped environment variable:

Windows PowerShell:

```powershell
$env:MAILVAULT_SECRET = Read-Host -AsSecureString
```

A PowerShell `SecureString` cannot be consumed directly as a normal environment variable. For unattended jobs, use an external secret manager that injects `MAILVAULT_SECRET` only into the child process and removes it after execution.

Do not commit secrets, `.env` files, App Passwords, private keys, exported mail, databases, or logs.

## Bandwidth caps

Caps are evaluated against a rolling 24-hour ledger maintained in the archive state directory. The soft cap stops normal acquisition cleanly. The hard cap prevents further raw fetches.

Accepted units include `B`, `KB`, `MB`, `GB`, `TB`, `KiB`, `MiB`, `GiB`, and `TiB`.

## Output controls

`write_per_message_json` creates readable derived metadata under `metadata/messages`.

`write_jsonl_exports` regenerates portable manifests after a successful run. They can also be rebuilt later with `mailvault export`.
