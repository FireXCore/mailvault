"""FireXCore MailVault: provider-neutral, evidence-preserving email archival."""

from __future__ import annotations

from importlib.metadata import PackageNotFoundError, version

__all__ = ["__version__"]


def _distribution_version() -> str:
    try:
        return version("firexcore-mailvault")
    except PackageNotFoundError:
        return "0.0.0+uninstalled"


__version__ = _distribution_version()
