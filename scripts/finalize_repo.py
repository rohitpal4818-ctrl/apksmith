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

#: Files that still carry a placeholder, and the token they carry.
TARGETS = {
    "pyproject.toml": "YOUR-USERNAME",
    "CHANGELOG.md": "YOUR-USERNAME",
    "CONTRIBUTING.md": "<your-fork>",
}

#: GitHub rejects a workspace named with these characters.
INVALID_USERNAME = re.compile(r"[^A-Za-z0-9-]")


def substitute(text: str, username: str) -> str:
    return (
        text.replace("YOUR-USERNAME", username)
        .replace("<your-fork>", username)
        .replace("YOUR-EMAIL", username)
    )


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
        ("placeholders replaced", not leftovers,
         "none" if not leftovers else ", ".join(f"{n}:{l}" for n, l in leftovers))
    )

    for filename in ("README.md", "LICENSE", "CONTRIBUTING.md", "CHANGELOG.md",
                     "SECURITY.md", "docs/ARCHITECTURE.md"):
        results.append(
            (f"{filename} present", (ROOT / filename).is_file(), "")
        )

    results.append(
        (".github/workflows/ci.yml present",
         (ROOT / ".github/workflows/ci.yml").is_file(), "")
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
    results.append(
        ("no stray binaries to commit", not stray, ", ".join(stray[:5]))
    )

    return results


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("username", nargs="?", help="your GitHub username")
    parser.add_argument(
        "--check", action="store_true",
        help="report status without changing any file",
    )
    args = parser.parse_args()

    if args.check or not args.username:
        print("status\n")
        for label, passed, detail in checks():
            mark = "ok  " if passed else "TODO"
            line = f"  [{mark}] {label}"
            if detail:
                line += f"  ({detail})"
            print(line)
        if not args.username:
            print("\nrun with a username to replace placeholders:")
            print("    python scripts/finalize_repo.py <github-username>")
        return 0 if all(p for _, p, _ in checks()) else 1

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