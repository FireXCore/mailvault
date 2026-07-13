# Data model

<p align="center">
  <img src="assets/evidence-model.svg" alt="MailVault evidence model" width="100%">
</p>

## Canonical message

A canonical message represents one archived raw message object. It contains:

- MailVault archive UUID;
- provider message and thread identity namespaces and values;
- RFC Message-ID, In-Reply-To and References;
- raw SHA-256, size and path;
- subject and dates;
- body extraction metadata;
- archive state.

## Mailbox occurrence

An occurrence represents a message observed in one mailbox generation:

```text
account
mailbox
UIDVALIDITY
UID
flags
labels
internal date
modification sequence
```

This separation prevents duplicate counting when one canonical message appears under multiple labels or mailboxes.

## Participants

Participants are ordered and role-specific:

```text
from
sender
reply_to
to
cc
bcc
```

Display name, normalized address and domain are stored separately. Public email domains are not automatically treated as organizations.

## MIME part

A MIME part records:

- hierarchical part path;
- parent part path;
- role;
- declared and detected MIME type;
- Content-Disposition and Content-ID;
- original and safe filenames;
- charset and transfer encoding;
- size and SHA-256;
- blob path;
- parsed headers and defects.

## Blob

A blob is a unique SHA-256-addressed payload. The same blob can be linked to many MIME-part occurrences.

## Evidence anchor

A downstream fact should store at least:

```text
message archive ID
raw EML SHA-256
MIME part path
blob SHA-256 when applicable
source filename
source dates
extractor name and version
confidence and review state
```

For document-level extraction, add page, sheet, cell range, text span or bounding box.
