"""CLI argument validation for `apksmith understand run`.

Both cases here used to fail badly rather than early:

- An unknown ``--provider`` hit a bare dict lookup, producing a ``KeyError``
  traceback -- but only *after* jadx had spent a minute decompiling.
- A ``--decompiled`` path that did not exist was accepted with the message
  "using existing decompiled sources", then failed later somewhere that read
  like a parser bug.

Neither needs a real APK, a key, or jadx, because both are rejected before any
work starts. The APK argument itself does declare ``exists=True``, so these
tests hand it a real (if empty) file to get past that check.
"""

from __future__ import annotations

from typer.testing import CliRunner

from apksmith.cli import cli as app

runner = CliRunner()


def _fake_apk(tmp_path):
    """The APK argument is validated by Click; give it something real."""
    apk = tmp_path / "fake.apk"
    apk.write_bytes(b"PK\x03\x04 not a real zip")
    return apk


def test_unknown_provider_is_rejected_before_any_work(tmp_path):
    result = runner.invoke(
        app,
        [
            "understand",
            "run",
            str(_fake_apk(tmp_path)),
            "--provider",
            "anthropic",
        ],
    )
    assert result.exit_code != 0
    combined = result.output + str(result.exception or "")
    assert "unknown provider" in combined
    assert "groq" in combined
    assert "openrouter" in combined


def test_unknown_provider_does_not_decompile(tmp_path):
    """The point of validating early: no wasted jadx run."""
    result = runner.invoke(
        app,
        [
            "understand",
            "run",
            str(_fake_apk(tmp_path)),
            "--provider",
            "nope",
            "--verbose",
        ],
    )
    assert "decompil" not in result.output.lower()


def test_decompiled_path_must_be_a_directory(tmp_path):
    missing = tmp_path / "not-here"
    result = runner.invoke(
        app,
        [
            "understand",
            "run",
            str(_fake_apk(tmp_path)),
            "--decompiled",
            str(missing),
        ],
    )
    assert result.exit_code != 0
    combined = result.output + str(result.exception or "")
    assert "not a directory" in combined


def test_decompiled_path_rejects_a_file(tmp_path):
    """A file is not a source tree either."""
    not_a_dir = tmp_path / "file.txt"
    not_a_dir.write_text("x", encoding="utf-8")
    result = runner.invoke(
        app,
        [
            "understand",
            "run",
            str(_fake_apk(tmp_path)),
            "--decompiled",
            str(not_a_dir),
        ],
    )
    assert result.exit_code != 0
    combined = result.output + str(result.exception or "")
    assert "not a directory" in combined
