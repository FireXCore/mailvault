# Operations

## Preflight

Run `mailvault doctor` before a new provider or account.

Confirm:

- TLS endpoint and port;
- authentication success;
- provider profile;
- advertised capabilities;
- selectable mailbox count;
- intended archive roots.

## Initial archive

Use a dedicated destination per account. Do not mix unrelated accounts in a directory unless the integration explicitly requires a shared archive.

For complete procurement history, use `scope=all`. Attachment-only scopes can omit commercial decisions contained only in message bodies.

## Resume

MailVault records metadata and raw completion independently. After interruption, run the same command against the same destination. Do not delete the database, state, or object directories.

## Bandwidth control

The throttling layer applies:

- bounded metadata batches;
- one raw acquisition stream;
- randomized per-message delay;
- periodic pauses;
- exponential retry;
- rolling 24-hour soft and hard caps.

Provider limits and account policies remain authoritative. Reduce caps and increase delays when a provider is sensitive to sustained IMAP activity.

## Verification

Full verification:

```bash
mailvault verify --destination /archive/path
```

Sample verification:

```bash
mailvault verify --destination /archive/path --sample 0.1
```

Use full verification before migration, backup handoff or RMS ingestion.

## Backup

Back up the entire archive root. The database without object storage is incomplete, and object storage without the database loses provenance.

## Log review

Operational logs are structured JSONL. They intentionally exclude message bodies and secrets. Protect logs because filenames, addresses and provider metadata can still be sensitive.

## Derived-output recovery

Rebuild manifests:

```bash
mailvault export --destination /archive/path
```

Rebuild navigation views:

```bash
mailvault views --destination /archive/path
```
