# Security model

## Trust boundaries

Mail servers, message headers, HTML bodies, MIME structures, filenames, charsets, attachments and nested messages are untrusted.

The local archive contains sensitive material and must be protected as confidential data.

## Credential model

MailVault supports interactive hidden input and a process-scoped `MAILVAULT_SECRET` variable. Secrets are not written to:

- TOML configuration;
- SQLite;
- message JSON;
- JSONL manifests;
- reports;
- logs;
- view pointers.

## Network security

Implicit TLS validates server certificates. STARTTLS is available only when explicitly configured. Plaintext IMAP is not supported.

## Read-only protocol surface

MailVault uses mailbox selection and fetch/search operations. It intentionally exposes no command for:

- delete;
- expunge;
- move;
- copy;
- append;
- send;
- flag mutation;
- label mutation.

Raw messages use PEEK semantics to avoid marking messages as read.

## Filesystem safety

Canonical paths are digest-based. Untrusted filenames are metadata, not storage paths. Disposable view segments are sanitized and bounded.

Object writes are atomic. Existing digest paths are checked for conflicting size before reuse.

## MIME handling

MailVault preserves rather than executes content. It does not:

- render active HTML;
- run macros;
- open Office documents;
- execute attachments;
- decrypt S/MIME or PGP;
- automatically expand arbitrary archives;
- automatically parse `winmail.dat` content.

Downstream processors must run in isolation with explicit resource limits and access policy.

## Sensitive repository hygiene

Never commit real mailbox exports, EML files, SQLite archives, logs, quotations, bank records, CVs, customer data, credentials or private certificates.

GitHub repository settings should enable secret scanning, push protection, Dependabot alerts, private vulnerability reporting and branch protection.
