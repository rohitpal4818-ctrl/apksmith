"""Guard against committing a live API key.

A key pasted into a source file, a report or a fixture is a working credential
the moment it is pushed, and git remembers it after it is deleted. This test
fails if any tracked text file contains a string shaped like a real key from a
provider this project can talk to.

Placeholders are deliberately not matched. The patterns require a long run of
key characters, so ``sk-or-v1-...`` and ``gsk_your_key_here`` pass while an
actual key does not. That distinction is the whole point: a test that also
matched the documentation would be turned off within a week.
"""

from __future__ import annotations

import re
import subprocess
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent

#: Shapes of real keys, one per provider the project supports or could grow to.
KEY_PATTERNS = {
    "openrouter": re.compile(r"sk-or-v1-[0-9a-f]{32,}"),
    "groq": re.compile(r"gsk_[A-Za-z0-9]{40,}"),
    "openai": re.compile(r"sk-[A-Za-z0-9]{40,}"),
    "anthropic": re.compile(r"sk-ant-[A-Za-z0-9_-]{20,}"),
    "github": re.compile(r"ghp_[A-Za-z0-9]{36,}"),
    "google": re.compile(r"AIza[0-9A-Za-z_-]{35}"),
}

#: Skip binaries and vendored trees; nothing there should be a key anyway, and
#: decoding them would fail.
SKIP_SUFFIXES = {".apk", ".jar", ".zip", ".png", ".jpg", ".ico", ".pdf", ".so", ".dex"}


def _tracked_text_files() -> list[Path]:
    """Every file git would actually commit, excluding binaries."""
    try:
        listed = subprocess.run(
            ["git", "ls-files", "-z"],
            cwd=REPO_ROOT,
            capture_output=True,
            check=True,
            timeout=60,
        ).stdout
    except (
        OSError,
        subprocess.SubprocessError,
    ) as exc:  # pragma: no cover - env dependent
        pytest.skip(f"git is unavailable, cannot enumerate tracked files: {exc}")

    files = []
    for raw in listed.split(b"\0"):
        if not raw:
            continue
        path = REPO_ROOT / raw.decode("utf-8", "replace")
        if path.suffix.lower() in SKIP_SUFFIXES:
            continue
        files.append(path)
    return files


def test_no_tracked_file_contains_a_real_key() -> None:
    """A real key in a tracked file is a leak, whether or not it is pushed yet."""
    findings: list[str] = []

    for path in _tracked_text_files():
        try:
            text = path.read_text(encoding="utf-8")
        except (UnicodeDecodeError, OSError):
            continue

        for provider, pattern in KEY_PATTERNS.items():
            for match in pattern.finditer(text):
                findings.append(
                    f"{path.relative_to(REPO_ROOT)}: looks like a live {provider} key "
                    f"({match.group()[:8]}...)"
                )

    assert not findings, (
        "a tracked file contains what looks like a real API key:\n  "
        + "\n  ".join(findings)
        + "\n\nRemove it, rotate the key, and keep it in the environment instead."
    )
