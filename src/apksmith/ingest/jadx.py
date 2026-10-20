"""
Optional decompilation via jadx.

jadx turns DEX bytecode into readable Java. That matters for the later LLM
stages: a model reasons about readable source far better than about smali.

jadx is treated as optional. APKSmith must work without it -- the static
analysers only need androguard. Callers check `is_available()` first.

Install
-------
Download the Windows build from https://github.com/skylot/jadx/releases,
unzip somewhere permanent, and either put ``jadx`` on PATH or pass an explicit
path. No admin rights needed.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import tempfile
from pathlib import Path

from ..errors import JadxFailed, JadxUnavailable

#: Candidate executable names per platform.
_CANDIDATES = ("jadx", "jadx.bat", "jadx.exe")

#: jadx prints progress to stderr; cap it so a huge APK cannot flood memory.
_MAX_LOG_BYTES = 64 * 1024


def is_available(explicit_path: str | os.PathLike[str] | None = None) -> bool:
    """True if we can find a runnable jadx."""
    if explicit_path and Path(explicit_path).exists():
        return True
    return any(shutil.which(name) for name in _CANDIDATES)


def resolve_binary(explicit_path: str | os.PathLike[str] | None = None) -> str:
    """Return a runnable jadx command, or raise JadxUnavailable."""
    if explicit_path:
        p = Path(explicit_path)
        if p.exists():
            return str(p)
        raise JadxUnavailable(f"jadx path does not exist: {p}")

    for name in _CANDIDATES:
        found = shutil.which(name)
        if found:
            return found

    raise JadxUnavailable(
        "jadx not found. Install it from "
        "https://github.com/skylot/jadx/releases or pass --jadx-path."
    )


def decompile(
    apk_path: str | os.PathLike[str],
    out_dir: str | os.PathLike[str] | None = None,
    jadx_path: str | os.PathLike[str] | None = None,
    timeout: int = 600,
) -> Path:
    """Decompile an APK to Java source.

    Parameters
    ----------
    apk_path
        The APK to decompile.
    out_dir
        Where to write sources. A temp dir is used and deleted by the caller.
    jadx_path
        Explicit jadx executable, if not on PATH.
    timeout
        Seconds before giving up. Large apps legitimately take minutes.

    Returns
    -------
    Path
        Directory containing the decompiled sources.

    Notes
    -----
    We deliberately avoid ``--no-res`` and keep resources, because later
    stages need layouts and strings to understand UI structure.
    """
    binary = resolve_binary(jadx_path)
    src = Path(apk_path)
    dest = Path(out_dir) if out_dir else Path(tempfile.mkdtemp(prefix="apksmith-jadx-"))
    dest.mkdir(parents=True, exist_ok=True)

    cmd = [binary, str(src), "--output-dir", str(dest), "--comments-level", "warn"]

    try:
        proc = subprocess.run(
            cmd,
            capture_output=True,
            timeout=timeout,
            check=False,
        )
    except subprocess.TimeoutExpired as exc:
        raise JadxFailed(f"jadx timed out after {timeout}s") from exc

    # jadx often returns non-zero for partially-decompilable apps while still
    # writing usable output. Treat it as success if sources appeared.
    produced_java = any(dest.rglob("*.java"))
    if not produced_java:
        tail = (proc.stderr or b"")[-_MAX_LOG_BYTES:].decode("utf-8", "replace")
        raise JadxFailed(
            f"jadx produced no Java sources (exit {proc.returncode}).\n{tail.strip()}",
            proc.returncode,
        )

    return dest
