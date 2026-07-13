# ADR 0003: MIME payloads use content-addressed storage

Status: Accepted

## Context

Filenames are untrusted, frequently duplicated, and do not represent stable content identity.

## Decision

Non-body MIME payloads are stored by SHA-256. Message-part records retain original filenames and every occurrence.

## Consequences

- Duplicate bytes consume storage once.
- All provenance remains queryable.
- Version labels are not fabricated from filename collisions.
