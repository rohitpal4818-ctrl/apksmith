"""Tests for the one-time repository finalizer.

The bug worth pinning: `git clone <your-fork> apksmith` was substituted to
`git clone rohit apksmith` -- a syntactically valid command that would clone
nothing. The replacement ran fine and left a broken file behind, which is why
`unknown_placeholders` scans for placeholder *shape* rather than relying on a
hand-maintained token list.

`scripts/` is not a package, so the module is loaded by path.
"""

from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest

SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "finalize_repo.py"


def _load():
    spec = importlib.util.spec_from_file_location("finalize_repo", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="module")
def finalizer():
    return _load()


# --------------------------------------------------------------------------- #
# However the placeholder appears, the result must be a usable value
# --------------------------------------------------------------------------- #
def test_substitute_fills_every_known_token(finalizer):
    filled = finalizer.substitute(
        "https://github.com/YOUR-USERNAME/apksmith", "rohit-pal"
    )
    assert filled == "https://github.com/rohit-pal/apksmith"


def test_substitute_leaves_unrelated_text_alone(finalizer):
    text = 'pip install -e ".[dev]"\n'
    assert finalizer.substitute(text, "someone") == text


def test_clone_command_becomes_a_real_url(finalizer):
    """The regression: `<your-fork>` was replaced with a bare username."""
    before = "git clone <your-fork> apksmith"
    # `<your-fork>` is no longer a known token, so it must be *detected*,
    # not silently substituted into something broken.
    assert finalizer.PLACEHOLDER.search(before)

    # And the shipped form is URL-shaped, so a bare username is correct.
    shipped = "git clone https://github.com/YOUR-USERNAME/apksmith.git apksmith"
    after = finalizer.substitute(shipped, "rohit-pal")
    assert after == "git clone https://github.com/rohit-pal/apksmith.git apksmith"
    assert finalizer.PLACEHOLDER.search(after) is None


# --------------------------------------------------------------------------- #
# The shape scan
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize(
    "text",
    ["<your-fork>", "YOUR-EMAIL", "YOUR-NAME", "<your-repo>"],
)
def test_placeholder_shapes_are_recognised(finalizer, text):
    assert finalizer.PLACEHOLDER.search(text)


@pytest.mark.parametrize(
    "text",
    ["your-username", "Your Username", "https://github.com/someone/apksmith"],
)
def test_ordinary_text_is_not_a_placeholder(finalizer, text):
    assert finalizer.PLACEHOLDER.search(text) is None


def test_known_tokens_are_excluded_from_the_unknown_scan(finalizer):
    """`remaining()` owns the known tokens; the shape scan owns the rest.

    Without this split, the finalizer's own TARGETS table would report itself
    as an unfilled placeholder.
    """
    assert {"YOUR-USERNAME"} <= finalizer.KNOWN_TOKENS
    source = SCRIPT.read_text(encoding="utf-8")
    scanned = [
        match
        for match in finalizer.PLACEHOLDER.findall(source)
        if match not in finalizer.KNOWN_TOKENS
    ]
    assert scanned == [], f"finalizer would flag itself: {scanned}"


def test_this_repository_has_no_unknown_placeholders(finalizer):
    """The real check, run against the real tree."""
    found = finalizer.unknown_placeholders()
    assert found == [], f"unknown placeholders: {found}"


def test_scan_skips_vendored_and_test_directories(finalizer):
    assert {"tools", ".venv", ".git", "samples", "tests"} <= finalizer.SCAN_SKIP


# --------------------------------------------------------------------------- #
# Username validation
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize(
    "username", ["rohit-pal-399a33426", "a", "user123", "with-hyphen"]
)
def test_valid_usernames_pass(finalizer, username):
    assert finalizer.INVALID_USERNAME.search(username) is None


@pytest.mark.parametrize(
    "username", ["bad user", "has_underscore", "dot.name", "slash/es", ""]
)
def test_invalid_usernames_are_rejected(finalizer, username):
    if username == "":
        # An empty username is caught by argparse, not the regex.
        pytest.skip("empty string is handled before the regex")
    assert finalizer.INVALID_USERNAME.search(username) is not None
