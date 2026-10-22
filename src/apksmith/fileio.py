"""Output helpers shared by the CLI commands.

Every artefact this tool writes is text: reports, behaviour specs, generated
Dart, evaluation results. They all go through :func:`write_text` so that three
things stay true in one place rather than four:

* parent directories are created, because ``--out build/recon/x.md`` should
  work on a fresh checkout;
* the encoding is UTF-8, so reports containing ``→`` or an app's non-ASCII
  label do not depend on the platform's default codepage;
* the line ending is ``\\n``, so a report produced on Windows is byte-identical
  to one produced on Linux. ``Path.write_text`` would otherwise translate to
  ``os.linesep``, and a caller that already holds ``\\r\\n`` would carry it
  through untouched, so both the newline argument and an explicit
  normalisation are needed.
"""

from __future__ import annotations

from pathlib import Path


def write_text(path: Path, content: str) -> Path:
    """Write ``content`` to ``path`` as UTF-8 with LF endings.

    Any ``\\r\\n`` or lone ``\\r`` in ``content`` is normalised to ``\\n`` first.
    Without that step the guarantee would only cover text this tool generated
    itself, and a report assembled from a file authored on Windows would still
    land on disk with CRLF.

    Returns the path, so callers can echo what was written without repeating
    it.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    normalised = content.replace("\r\n", "\n").replace("\r", "\n")
    path.write_text(normalised, encoding="utf-8", newline="\n")
    return path
