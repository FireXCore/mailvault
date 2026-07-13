# Roadmap

## Archive core

- Stabilize schema migration policy.
- Add documented offline importers for EML, MBOX and Maildir.
- Add optional encrypted archive-at-rest integration without embedding key management in the core.
- Add export packaging with checksum manifests.

## Provider adapters

- OAuth 2.0 authentication framework.
- Microsoft 365 adapter.
- JMAP adapter.
- Additional provider contract fixtures.

## Operations

- Structured run report with per-mailbox throughput and retry statistics.
- Configurable provider-specific rate profiles.
- Optional daemon mode for incremental sync.
- Optional metrics export.

## Procurement ecosystem

The following belong in separate packages, not the core archive:

- `mailvault-procurement` for evidence-backed classification and fact extraction;
- `mailvault-rms` for RMS ACL mapping, review workflow and idempotent ingestion;
- native document parsers;
- selective OCR/VLM workers;
- supplier identity resolution;
- price normalization;
- technical substitution graph.
