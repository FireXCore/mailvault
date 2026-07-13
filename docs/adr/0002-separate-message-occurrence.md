# ADR 0002: Canonical messages and mailbox occurrences are separate

Status: Accepted

## Context

Gmail labels, generic IMAP folders, moves and duplicate mailbox representations can cause one logical message to appear more than once.

## Decision

A canonical message is stored separately from mailbox occurrences keyed by account, mailbox generation, UIDVALIDITY and UID.

## Consequences

- Downstream supplier response metrics avoid duplicate counting.
- Provider labels and folder evidence remain preserved.
- Message movement does not require rewriting canonical raw objects.
