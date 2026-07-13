# Troubleshooting

## `mailvault` is not recognized

Activate the intended virtual environment and install the package from the directory containing `pyproject.toml`:

```powershell
.\.venv\Scripts\Activate.ps1
python -m pip install -e .
Get-ChildItem .\.venv\Scripts\mailvault*
```

Fallback module form:

```powershell
python -m firexcore_mailvault version
```

## `pip show` and `mailvault version` disagree

The CLI version is single-sourced from installed distribution metadata in version 2.0.3 and newer. Reinstall the current checkout:

```powershell
python -m pip uninstall -y firexcore-mailvault
python -m pip install --no-deps --force-reinstall -e .
```

Then verify:

```powershell
python -m pip show firexcore-mailvault
mailvault version
python -m firexcore_mailvault version
```

## Invalid value for `--auth`

`--auth` receives a mode, not the secret:

```text
--auth app-password
--auth password
```

The secret is requested afterward through hidden input.

## Gmail authentication fails

Confirm:

- IMAP access is permitted for the account;
- two-step verification is enabled when App Passwords are required;
- a current App Password is used;
- the account address is complete;
- the server is `imap.gmail.com` on port 993 with implicit TLS.

Revoke any App Password pasted into a command, chat, log or screenshot.

## Malformed legacy headers

MailVault uses a tolerant header path and sanitizes derived Unicode metadata. Raw EML remains untouched. If a message still fails, preserve the traceback and the structured log record, but do not share the real EML publicly. Create a synthetic fixture reproducing the malformed header.

## Archive appears stalled during metadata discovery

Metadata discovery can process many messages before raw downloads begin. Observe the metadata counter and logs. Large Gmail archives may report `Raw 0` until sufficient metadata has been committed.

## Existing partial archive

Do not delete it. Run the same version and command against the same destination. MailVault resumes using stored metadata, occurrences and raw completion state.

## Integrity verification fails

Do not continue with downstream ingestion. Check missing paths, storage corruption, interrupted external copy operations, antivirus quarantine and filesystem errors. Restore canonical objects from backup, then rerun full verification.
