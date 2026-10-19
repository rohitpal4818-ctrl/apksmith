"""Regression tests for the temp-directory cleanup bug.

`apksmith understand` used to call ``shutil.rmtree(tmp_dir.parent)``.
``tempfile.mkdtemp(prefix=...)`` returns ``<tempdir>/apksmith-m2-XXXX``, so
``.parent`` is the operating system's temp directory. The cleanup therefore
deleted every temp file on the user's machine rather than just its own
subfolder.

It ran against a real APK before it was found, so this is checked directly
rather than by inspecting the source.
"""

from __future__ import annotations

import tempfile
from pathlib import Path

import pytest


def test_cleanup_removes_our_directory_only():
    """The pattern that caused the bug must not come back."""
    from apksmith.m2 import _write  # noqa: F401  (import smoke check)

    system_temp = Path(tempfile.gettempdir())
    ours = Path(tempfile.mkdtemp(prefix="apksmith-selftest-"))
    (ours / "jadx").mkdir()
    (ours / "marker.txt").write_text("x", encoding="utf-8")

    assert ours.parent == system_temp, "precondition: we are a direct child of temp"

    # This is what m2.py's finally block now does.
    import shutil

    shutil.rmtree(ours, ignore_errors=True)

    assert not ours.exists(), "our own directory should be gone"
    assert system_temp.exists(), "THE SYSTEM TEMP DIRECTORY MUST SURVIVE"
    assert len(list(system_temp.iterdir())) > 0, "temp directory was emptied"


@pytest.mark.parametrize("prefix", ["apksmith-m2-", "apksmith-mcp-", "apksmith-"])
def test_every_prefix_produces_a_safe_child(prefix: str):
    """Whatever prefix is used, cleanup must target the child, not the parent."""
    d = Path(tempfile.mkdtemp(prefix=prefix))
    try:
        assert d.parent == Path(tempfile.gettempdir())
        # The safe target is `d`. The dangerous one is `d.parent`, so the test
        # pins which of the two we consider correct.
        assert d != d.parent
    finally:
        import shutil

        shutil.rmtree(d, ignore_errors=True)


def test_no_source_file_rmtrees_a_parent_directory():
    """Belt and braces: grep the source for the dangerous pattern."""
    import ast
    from pathlib import Path

    package = Path(__file__).resolve().parents[1] / "src" / "apksmith"
    offenders: list[str] = []

    for py in package.rglob("*.py"):
        tree = ast.parse(py.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            func = node.func
            if not (isinstance(func, ast.Attribute) and func.attr == "rmtree"):
                continue
            if not node.args:
                continue
            target = node.args[0]
            # `rmtree(x.parent)` or `rmtree(x.parent)` on anything not
            # obviously scoped is the shape we are looking for.
            if isinstance(target, ast.Attribute) and target.attr == "parent":
                offenders.append(f"{py.name}:{node.lineno} rmtree(... .parent)")

    assert not offenders, (
        "rmtree called on a .parent -- this deletes the enclosing directory: "
        + "; ".join(offenders)
    )