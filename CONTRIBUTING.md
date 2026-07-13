# Contributing

FireXCore MailVault accepts focused contributions that preserve evidence integrity, read-only behavior and provider neutrality.

## Before opening a pull request

- Search existing issues and pull requests.
- Open a design issue before introducing a new provider, protocol, archive schema, authentication mechanism or dependency.
- Never attach real mailbox data to an issue or pull request.
- Reproduce parser failures with synthetic, sanitized fixtures.

## Development setup

```bash
python -m venv .venv
source .venv/bin/activate
python -m pip install -e '.[dev]'
python scripts/quality.py
```

Windows PowerShell:

```powershell
py -3.13 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -e '.[dev]'
python scripts/quality.py
```

## Required design rules

- Preserve raw evidence before deriving data.
- Keep protocol/provider code outside archive-domain code.
- Do not use RFC Message-ID as the sole canonical identity.
- Keep canonical messages separate from mailbox occurrences.
- Do not add IMAP mutation commands.
- Do not persist credentials.
- Store untrusted payloads by digest, not by filename.
- Every schema change requires tests, compatibility handling and data-model documentation.
- Every provider change requires provider contract tests.
- Procurement extraction belongs in a downstream package; the core remains domain-neutral.

## Pull request requirements

A pull request must include:

- a precise problem statement;
- tests covering success and failure behavior;
- documentation for public behavior changes;
- changelog entry when user-visible;
- no real credentials, addresses, message content, company names or customer data;
- successful execution of `python scripts/quality.py`.

## Commit style

Use direct, descriptive commit messages:

```text
fix: tolerate malformed RFC address groups
feat: preserve OBJECTID thread identifiers
refactor: isolate provider mailbox selection
build: validate wheel metadata in release gate
```

## Test fixtures

Fixtures must be synthetic and sanitized. Never commit real customer email, credentials, personal data, banking data, quotations, CVs, contracts or company-confidential attachments.

## Security reports

Do not disclose vulnerabilities through a public issue. Follow [SECURITY.md](SECURITY.md).
