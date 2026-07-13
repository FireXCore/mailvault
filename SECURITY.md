# Security policy

## Supported versions

Security fixes target the latest release and the `main` branch.

## Reporting vulnerabilities

Do not open a public issue for a vulnerability involving credentials, path traversal, archive corruption, unsafe MIME handling, unintended mailbox mutation, sensitive-data exposure or integrity bypass.

Use GitHub private vulnerability reporting for `FireXCore/mailvault`. Include:

- affected version;
- operating system and Python version;
- minimal synthetic reproduction;
- security impact;
- proposed mitigation when known.

Do not submit real EML, credentials or confidential attachments.

## Credential handling

- Passwords and App Passwords are collected through hidden input.
- Credentials are not stored in TOML, SQLite, JSON, manifests, reports or logs.
- `MAILVAULT_SECRET` is supported only as a process-scoped environment variable for controlled automation.
- Logs must never contain raw message bodies or authentication values.
- A secret exposed in a command, screenshot, issue, chat or log must be revoked immediately.

## Threat model

Mail content is untrusted. Attackers may control:

- filenames;
- MIME headers and nesting;
- charsets and malformed Unicode;
- HTML and embedded resources;
- attachment bytes;
- nested messages;
- protocol metadata;
- subjects and display names.

Implemented defenses include:

- content-addressed canonical paths independent of filenames;
- sanitized disposable view names;
- no automatic execution or rendering of attachments;
- no mutation commands in the IMAP gateway;
- TLS certificate validation;
- atomic object writes;
- SHA-256 integrity verification;
- explicit SQLite transactions and foreign keys;
- single-run archive locking;
- raw-byte preservation with derived-metadata sanitization.

## Current exclusions

MailVault does not currently:

- decrypt S/MIME or PGP content;
- expand arbitrary compressed archives;
- execute Office macros;
- render active HTML;
- extract TNEF payloads;
- provide encrypted key management;
- provide OAuth authentication.

Such payloads are preserved for isolated downstream processing.
