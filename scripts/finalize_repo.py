"""One-time repository finalisation.

Replaces the `YOUR-USERNAME` placeholders left in the project metadata, and
checks the things that are easy to forget before the first public push.

    python scripts/finalize_repo.py rohit-pal-399a33426
    python scripts/finalize_repo.py rohit-pal-399a33426 --check

`--check` reports what still needs doing without changing anything.
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

#: Tokens `substitute` knows how to fill. This is the single source of truth:
#: `substitute` builds its replacements from it, and `KNOWN_TOKENS` derives
#: from it, so a token cannot be replaceable in one place and unknown in the
#: other.
REPLACEMENT_TOKENS = ("YOUR-USERNAME", "YOUR-EMAIL")

#: Files that carry a placeholder. Every placeholder sits inside a URL, so a
#: bare username is the correct substitution everywhere. An earlier version
#: also had a bare fork placeholder in a shell command, which turned
#: `git clone <the-fork> apksmith` into `git clone rohit apksmith` -- a valid
#: command that would clone nothing. Keeping every site URL-shaped removes
#: that whole class of mistake, and `checks()` now scans for placeholder-shaped
#: text that TARGETS does not know about, so a new one cannot hide.
TARGETS = {
    "pyproject.toml": "YOUR-USERNAME",
    "CHANGELOG.md": "YOUR-USERNAME",
    "CONTRIBUTING.md": "YOUR-USERNAME",
}

#: Anything shaped like an unfilled placeholder. This is deliberately broader
#: than TARGETS: the `git clone` bug survived because the replacement ran
#: successfully and left a broken command behind. Only a scan for the *shape*
#: catches a token nobody remembered to list.
PLACEHOLDER = re.compile(r"YOUR-[A-Z][A-Z-]*|<your-[a-z-]+>")

#: Where placeholder-shaped text is legitimate, relative to ROOT. `tests` is
#: listed because fixtures in this very suite use placeholder strings on
#: purpose; they never ship.
SCAN_SKIP = {
    ".venv",
    ".git",
    "tools",
    "build",
    "dist",
    "samples",
    "tests",
    "node_modules",
}

#: Extensions worth scanning.
SCAN_SUFFIXES = {".md", ".toml", ".py", ".yml", ".yaml", ".cfg", ".txt"}

#: GitHub rejects a workspace named with these characters.
INVALID_USERNAME = re.compile(r"[^A-Za-z0-9-]")

#: Tokens TARGETS already knows about. Excluded from the generic scan, so the
#: only thing `unknown_placeholders` reports is placeholder-shaped text nobody
#: listed -- which is exactly the case that broke the clone command.
KNOWN_TOKENS = frozenset(REPLACEMENT_TOKENS) | frozenset(TARGETS.values())


def substitute(text: str, username: str) -> str:
    for token in REPLACEMENT_TOKENS:
        text = text.replace(token, username)
    return text


def unknown_placeholders() -> list[tuple[str, int, str]]:
    """Placeholder-shaped text that TARGETS does not already account for."""
    found: list[tuple[str, int, str]] = []
    for path in sorted(ROOT.rglob("*")):
        if not path.is_file() or path.suffix not in SCAN_SUFFIXES:
            continue
        if set(path.relative_to(ROOT).parts) & SCAN_SKIP:
            continue
        for number, line in enumerate(
            path.read_text(encoding="utf-8", errors="ignore").splitlines(), 1
        ):
            match = PLACEHOLDER.search(line)
            if match and match.group(0) not in KNOWN_TOKENS:
                found.append((str(path.relative_to(ROOT)), number, match.group(0)))
    return found


def remaining() -> list[tuple[str, int]]:
    """Files still holding a placeholder, with the line numbers."""
    out: list[tuple[str, int]] = []
    for name, token in TARGETS.items():
        path = ROOT / name
        if not path.is_file():
            continue
        for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
            if token in line:
                out.append((name, number))
    return out


def checks() -> list[tuple[str, bool, str]]:
    """Pre-push sanity checks. Each returns (label, passed, detail)."""
    results: list[tuple[str, bool, str]] = []

    leftovers = remaining()
    results.append(
        (
            "placeholders replaced",
            not leftovers,
            "none"
            if not leftovers
            else ", ".join(f"{n}:{line}" for n, line in leftovers),
        ),
    )

    unknown = unknown_placeholders()
    results.append(
        (
            "no unknown placeholders",
            not unknown,
            "none"
            if not unknown
            else ", ".join(f"{n}:{line} ({tok})" for n, line, tok in unknown),
        ),
    )

    for filename in (
        "README.md",
        "LICENSE",
        "CONTRIBUTING.md",
        "CHANGELOG.md",
        "SECURITY.md",
        "docs/ARCHITECTURE.md",
    ):
        results.append((f"{filename} present", (ROOT / filename).is_file(), ""))

    results.append(
        (
            ".github/workflows/ci.yml present",
            (ROOT / ".github/workflows/ci.yml").is_file(),
            "",
        )
    )

    # A stray binary must not be committed. Files that .gitignore already
    # covers (the sample APK, the local jadx bundle, build output) are
    # expected and are skipped -- this catches the case someone matters.
    already_ignored = {"samples", "tools", "build", ".venv", "dist", ".git"}
    stray = [
        str(p.relative_to(ROOT))
        for p in ROOT.rglob("*")
        if p.is_file()
        and p.suffix in {".apk", ".jar", ".zip"}
        and not (set(p.parts) & already_ignored)
    ]
    results.append(("no stray binaries to commit", not stray, ", ".join(stray[:5])))

    return results


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("username", nargs="?", help="your GitHub username")
    parser.add_argument(
        "--check",
        action="store_true",
        help="report status without changing any file",
    )
    args = parser.parse_args()

    if args.check or not args.username:
        results = checks()
        print("status\n")
        for label, passed, detail in results:
            mark = "ok  " if passed else "TODO"
            line = f"  [{mark}] {label}"
            if detail:
                line += f"  ({detail})"
            print(line)
        if not args.username:
            print("\nrun with a username to replace placeholders:")
            print("    python scripts/finalize_repo.py <github-username>")
        return 0 if all(p for _, p, _ in results) else 1

    username = args.username
    if INVALID_USERNAME.search(username):
        print(f"error: '{username}' is not a valid GitHub username", file=sys.stderr)
        return 2

    changed = []
    for name in TARGETS:
        path = ROOT / name
        if not path.is_file():
            continue
        original = path.read_text(encoding="utf-8")
        updated = substitute(original, username)
        if updated != original:
            path.write_text(updated, encoding="utf-8")
            changed.append(name)

    print(f"replaced placeholders in: {', '.join(changed) or 'nothing to change'}")
    print(f"\nrepository: https://github.com/{username}/apksmith")
    print("\nremaining checks:")
    for label, passed, detail in checks():
        mark = "ok  " if passed else "TODO"
        line = f"  [{mark}] {label}"
        if detail:
            line += f"  ({detail})"
        print(line)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
