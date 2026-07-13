# ADR 0001: Raw EML is the canonical message evidence

Status: Accepted

## Context

Attachment-only exports lose message boundaries, headers, body-only commercial decisions, MIME structure, thread evidence and attachment provenance.

## Decision

MailVault stores the exact raw message bytes returned by read-only IMAP acquisition as an immutable SHA-256-addressed EML object. Parsed metadata and extracted bodies are derived data.

## Consequences

- Parser defects do not destroy source evidence.
- Derived models can be regenerated.
- Storage requirements include complete messages, not only attachments.
- Sensitive archive handling is mandatory.
