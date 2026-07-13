# Repository setup

## Commit identity before the first push

GitHub attributes commits to the account that owns the commit email address. Verify the identity before creating the initial commit:

```bash
git config user.name
git config user.email
```

Set `user.name` and `user.email` to the intended maintainer account. Use a verified email address or the GitHub-provided no-reply address copied from the account email settings. Confirm the result before committing:

```bash
git config user.name "Farbod Akvan"
git config user.email "YOUR_VERIFIED_OR_NOREPLY_GITHUB_EMAIL"
git var GIT_AUTHOR_IDENT
```

After pushing the repository to `github.com/FireXCore/mailvault`, configure the following settings.

## General

- Description: `Provider-neutral, read-only email evidence archiving with immutable EML, MIME provenance and procurement-ready manifests.`
- Website: project documentation or PyPI page when available.
- Topics: `imap`, `email-archive`, `email-backup`, `gmail`, `evidence`, `ediscovery`, `procurement`, `python`, `sqlite`, `sha256`.
- Upload `docs/assets/social-preview.png` as the repository social preview.

## Branch protection

Protect `main` and require:

- pull request review;
- passing `CI` checks;
- conversation resolution;
- no force pushes;
- no branch deletion.

## Security

Enable:

- dependency graph;
- Dependabot alerts;
- Dependabot security updates;
- secret scanning;
- push protection;
- private vulnerability reporting;
- code scanning.

## Releases

Create Git tags in the form `v2.0.4`. The release workflow builds wheel and source distribution, validates metadata, writes SHA-256 checksums and attaches artifacts to the GitHub release.

PyPI publishing uses a separate trusted-publishing workflow. Configure the GitHub `pypi` environment and PyPI trusted publisher, then set the repository variable `PYPI_PUBLISH_ENABLED=true`. Manual dispatch remains available for controlled validation.

## Pages

The repository does not require GitHub Pages. Markdown documentation remains first-class and directly readable in GitHub. A documentation site can be added later without changing archive or package design.
