"""The documentation claim checker must keep passing, and must still be able
to fail.

A checker that only ever passes is decoration. The second test proves it can
still catch a stale phrase by pointing it at a copy of the docs with one
reintroduced.
"""

from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SCRIPT = ROOT / "scripts" / "check_docs.py"


def _run(cwd: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(SCRIPT)],
        cwd=cwd,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )


def test_documented_claims_match_the_repository():
    result = _run(ROOT)
    assert result.returncode == 0, result.stdout + result.stderr
    assert "All documented claims agree" in result.stdout


def test_checker_catches_a_reintroduced_stale_claim(tmp_path):
    # The checker resolves paths from its own location, so give it a tree that
    # looks like the repo with one wrong sentence put back.
    for relative in (
        "README.md",
        "CONTRIBUTING.md",
        "docs/ARCHITECTURE.md",
        "evaluation/suite.json",
        "reports/sample-evaluation.md",
        "reports/sample-f-droid.json",
        "src/apksmith/mcp_server.py",
    ):
        source = ROOT / relative
        target = tmp_path / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy(source, target)

    readme = tmp_path / "README.md"
    readme.write_text(
        readme.read_text(encoding="utf-8") + "\nThe extractor removes 97% of the text.\n",
        encoding="utf-8",
    )

    copied_script = tmp_path / "scripts" / "check_docs.py"
    copied_script.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy(SCRIPT, copied_script)

    result = subprocess.run(
        [sys.executable, str(copied_script)],
        cwd=tmp_path,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    assert result.returncode == 1, "the checker missed a stale claim"
    assert "97%" in result.stdout


def test_packaging_version_has_one_source():
    """pyproject must not restate the version.

    It once said 0.1.0 while `apksmith.__version__` said 0.2.0 and the CLI
    printed 0.2.0. The number a package index would have shown was the wrong
    one, because it came from the file nobody runs.
    """
    import tomllib

    import apksmith

    data = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))

    assert "version" in data["project"].get("dynamic", []), (
        "version is hard-coded in pyproject again; it will drift from the package"
    )
    attr = data["tool"]["setuptools"]["dynamic"]["version"]["attr"]
    assert attr == "apksmith.__version__"

    parts = apksmith.__version__.split(".")
    assert len(parts) == 3 and all(part.isdigit() for part in parts), (
        f"{apksmith.__version__!r} is not MAJOR.MINOR.PATCH"
    )
