# Archive format

## Root layout

```text
MailVault/
├── objects/raw/sha256/aa/bb/<digest>
├── objects/blobs/sha256/aa/bb/<digest>
├── metadata/messages/<archive-id>.json
├── database/mailvault.sqlite3
├── manifests/*.jsonl
├── state/*
├── reports/*
├── logs/*
└── views/*
```

## Raw message objects

A raw message object contains exactly the bytes returned by the read-only IMAP raw fetch. Its path is derived only from SHA-256:

```text
objects/raw/sha256/<first-2>/<next-2>/<full-digest>
```

A raw object is never named from sender, subject, Message-ID or attachment filename.

## Blob objects

Every stored non-body MIME payload is addressed by its SHA-256 digest. Multiple message parts can point to the same blob.

## SQLite database

SQLite is the operational index and relationship store. It records:

- accounts and providers;
- mailboxes and UIDVALIDITY generations;
- canonical messages;
- provider identities and thread identities;
- mailbox occurrences;
- participants;
- complete header evidence;
- MIME parts;
- blobs and message-part links;
- sync runs and checkpoints;
- bandwidth ledger entries.

## Derived per-message JSON

Per-message JSON is intended for inspection and integrations. It is not the authoritative copy of the raw message.

## JSONL manifests

JSONL files provide streaming and portable integration surfaces. They are regenerated in deterministic database order.

## Navigation views

Views contain pointer JSON, not duplicated attachment bytes. Their paths are sanitized for human navigation and are disposable.

## Portability

To transfer an archive:

1. Stop all writers.
2. Run a full `mailvault verify`.
3. Copy the entire archive root.
4. Run `mailvault verify` at the destination.
5. Preserve filesystem permissions appropriate to the sensitivity of the mailbox.
