# Development

## Environment

```bash
python -m venv .venv
source .venv/bin/activate
python -m pip install -e '.[dev]'
```

Windows PowerShell:

```powershell
py -3.13 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -e '.[dev]'
```

## Quality gate

```bash
python scripts/quality.py
```

Equivalent commands:

```bash
ruff check src tests
ruff format --check src tests
mypy src
pytest --cov=firexcore_mailvault --cov-report=term-missing
python -m build
```

## Design constraints

- Protocol adapters do not own archive persistence.
- Provider profiles do not parse procurement facts.
- Canonical objects are immutable.
- Raw EML is authoritative.
- RFC Message-ID is evidence, not the sole message key.
- Mailbox occurrence remains separate from canonical message.
- No IMAP mutation command may be introduced.
- Credentials must never enter persistent state.
- All schema changes require migrations or explicit compatibility handling, tests and data-model documentation.
- Fixtures must be synthetic and sanitized.

## Testing provider behavior

Provider tests should cover:

- capability parsing;
- archive-root selection;
- stable provider message identity;
- stable thread identity;
- label mapping;
- provider query translation;
- fallback behavior when extensions are absent.

## Release validation

Before tagging:

```bash
python scripts/quality.py
python scripts/release_check.py
```

The release check verifies package metadata, version consistency, clean repository exclusions, expected documentation and build artifacts.
