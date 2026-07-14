# Changelog

All notable changes to FireXCore MailVault are documented in this file.

The project follows Semantic Versioning.

## 2.0.5 - 2026-07-14

### Fixed

- Corrected Gmail full-scope discovery to use the standard IMAP `SEARCH ALL` criterion.
- Removed the invalid `X-GM-RAW "all"` behavior, which interpreted `all` as a Gmail text search and could silently omit older messages.
- Versioned scan selection keys so existing archives perform a safe full metadata rescan after upgrading instead of reusing the affected checkpoint.

### Added

- Added Gmail message-ID fetch support for remote label reconciliation.
- Added the `mailvault audit-labels` command to compare every IMAP-visible Gmail label with locally archived raw EML identities.
- Full-scope Gmail sync now runs the same remote label audit before reporting `complete`; missing remote messages produce `incomplete` and exit code 2.

## 2.0.4 - 2026-07-13

### Fixed

- Corrected the repository ignore policy so `src/firexcore_mailvault/archive/` is tracked and included in Git checkouts.
- Restored the content-addressed archive package in source checkouts and built distributions.
- Added repository source-completeness validation to prevent ignored or untracked Python modules from reaching a release.
- Verified wheel installation and CLI smoke tests from a clean environment.

### Repository

- Added commit identity verification instructions before the initial public commit.
- Kept runtime archive output ignored only at the repository root.

## 2.0.3 - 2026-07-13

### Fixed

- Single-sourced the CLI version from installed Python distribution metadata.
- Made `mailvault version`, `python -m firexcore_mailvault version`, and `pip show` report the same version.
- Added a callable CLI entry point instead of exposing the Typer application object directly.

### Documentation

- Rebuilt the repository README in a formal GitHub-ready format.
- Added complete installation, configuration, operations, security, provider, troubleshooting, development and repository setup documentation.
- Added Persian documentation.
- Added architecture, evidence-model, terminal example, logo, banner and social-preview assets.
- Added architecture decision records for raw EML, mailbox occurrences and content-addressed blobs.

### Repository

- Added formal pull request, issue, ownership, security scanning and release automation files.
- Added release and quality validation scripts.
- Updated CI for current GitHub Actions and Python 3.12 through 3.14.

## 2.0.2 - 2026-07-13

### Fixed

- Added tolerant parsing for malformed legacy address-group headers that can trigger Python `headerregistry` failures.
- Preserved raw header bytes while allowing metadata discovery to continue.

## 2.0.1 - 2026-07-13

### Fixed

- Sanitized invalid Unicode surrogate code points in derived metadata, JSON, SQLite and logs.
- Kept raw EML bytes unchanged.

## 2.0.0 - 2026-07-13

### Added

- Provider-neutral archive core.
- Gmail and generic IMAP provider profiles.
- Immutable raw EML storage.
- SHA-256 content-addressed attachment storage.
- SQLite evidence model.
- Resumable sync, throttling, verification, JSONL exports and procurement source manifests.
