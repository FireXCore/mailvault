from __future__ import annotations

import importlib.metadata
import re
import subprocess
import sys
import tomllib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
REQUIRED_FILES = (
    "README.md",
    "LICENSE",
    "NOTICE",
    "SECURITY.md",
    "CONTRIBUTING.md",
    "CHANGELOG.md",
    "docs/ARCHITECTURE.md",
    "docs/PROCUREMENT_READINESS.md",
    "docs/assets/banner.svg",
    "docs/assets/social-preview.png",
    ".github/workflows/ci.yml",
    ".github/workflows/release.yml",
    "src/firexcore_mailvault/archive/__init__.py",
    "src/firexcore_mailvault/archive/object_store.py",
)
FORBIDDEN_NAMES = {
    ".venv",
    ".pytest_cache",
    ".mypy_cache",
    ".ruff_cache",
    "__pycache__",
    "build",
    "dist",
}


def fail(message: str) -> None:
    raise SystemExit(f"release check failed: {message}")


def project_version() -> str:
    with (ROOT / "pyproject.toml").open("rb") as handle:
        return str(tomllib.load(handle)["project"]["version"])


def check_required_files() -> None:
    missing = [name for name in REQUIRED_FILES if not (ROOT / name).is_file()]
    if missing:
        fail(f"missing required files: {', '.join(missing)}")


def check_version() -> None:
    declared = project_version()
    installed = importlib.metadata.version("firexcore-mailvault")
    if declared != installed:
        fail(f"pyproject version {declared} does not match installed version {installed}")
    output = subprocess.check_output(
        [sys.executable, "-m", "firexcore_mailvault", "version"],
        cwd=ROOT,
        text=True,
    ).strip()
    if output != declared:
        fail(f"CLI version {output} does not match pyproject version {declared}")
    if not re.fullmatch(r"\d+\.\d+\.\d+", declared):
        fail(f"version is not a stable semantic version: {declared}")


def check_repository_cleanliness() -> None:
    git_dir = ROOT / ".git"
    if not git_dir.exists():
        return
    tracked = set(subprocess.check_output(["git", "ls-files"], cwd=ROOT, text=True).splitlines())
    generated = [
        name for name in tracked if any(part in FORBIDDEN_NAMES for part in Path(name).parts)
    ]
    if generated:
        fail(f"generated files are tracked: {', '.join(generated[:10])}")

    source_files = {
        path.relative_to(ROOT).as_posix()
        for path in (ROOT / "src" / "firexcore_mailvault").rglob("*.py")
    }
    untracked_source = sorted(source_files - tracked)
    if untracked_source:
        fail("Python source files are ignored or untracked: " + ", ".join(untracked_source[:10]))


def main() -> None:
    check_required_files()
    check_version()
    check_repository_cleanliness()
    print("release check passed")


if __name__ == "__main__":
    main()
