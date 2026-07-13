from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def run(*command: str) -> None:
    print(f"+ {' '.join(command)}", flush=True)
    subprocess.run(command, cwd=ROOT, check=True)


def main() -> None:
    python = sys.executable
    for generated in (ROOT / "build", ROOT / "dist"):
        shutil.rmtree(generated, ignore_errors=True)
    for egg_info in ROOT.glob("*.egg-info"):
        shutil.rmtree(egg_info, ignore_errors=True)

    run(python, "-m", "ruff", "check", "src", "tests", "scripts")
    run(python, "-m", "ruff", "format", "--check", "src", "tests", "scripts")
    run(python, "-m", "mypy", "src")
    run(
        python,
        "-m",
        "pytest",
        "--cov=firexcore_mailvault",
        "--cov-report=term-missing",
    )
    run(python, "scripts/release_check.py")
    run(python, "-m", "build")
    artifacts = sorted(str(path) for path in (ROOT / "dist").iterdir() if path.is_file())
    run(python, "-m", "twine", "check", *artifacts)


if __name__ == "__main__":
    main()
