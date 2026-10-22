"""Direct tests for the one function that writes every artefact.

`test_generate_eval.py` checks that a generated project has no CRLF on disk, but
that only proves the templates happen not to contain one. This file tests the
writer itself: hand it CRLF and it must still produce LF, because a report
assembled from a Windows source file would otherwise carry ``\\r\\n`` into the
committed sample output and break byte reproducibility.

The encoding test exists for the same reason. An app label or a URL can be
non-ASCII, and the platform's default codepage must never be what decides
whether the file is readable on another machine.
"""

from __future__ import annotations

from pathlib import Path

from apksmith.fileio import write_text


def test_crlf_input_is_written_as_lf(tmp_path: Path):
    """A Windows-style string must not reach disk with CRLF."""
    path = write_text(tmp_path / "report.md", "line one\r\nline two\r\n")

    assert path.read_bytes() == b"line one\nline two\n"


def test_utf8_survives_every_platform(tmp_path: Path):
    """Non-ASCII text is written as UTF-8, with no byte-order mark."""
    text = "arrow \u2192 and a label: \u0939\u093f\u0928\u094d\u0926\u0940"

    path = write_text(tmp_path / "spec.md", text)

    assert path.read_bytes() == text.encode("utf-8")
    assert not path.read_bytes().startswith(b"\xef\xbb\xbf"), "a BOM was written"


def test_parent_directories_are_created(tmp_path: Path):
    """``--out build/recon/x.md`` must work on a fresh checkout."""
    path = write_text(tmp_path / "build" / "recon" / "deep" / "out.md", "x")

    assert path.exists()
    assert path.read_text(encoding="utf-8") == "x"


def test_returns_the_path_it_wrote(tmp_path: Path):
    """Callers echo the returned path, so it must be the file, not a guess."""
    target = tmp_path / "nested" / "result.json"

    assert write_text(target, "{}") == target
