from __future__ import annotations

from importlib.metadata import version

from typer.testing import CliRunner

from firexcore_mailvault import __version__
from firexcore_mailvault.cli import app


def test_package_version_is_single_sourced_from_distribution_metadata() -> None:
    assert __version__ == version("firexcore-mailvault")


def test_version_command_matches_distribution_metadata() -> None:
    result = CliRunner().invoke(app, ["version"])

    assert result.exit_code == 0
    assert result.stdout.strip() == version("firexcore-mailvault")
