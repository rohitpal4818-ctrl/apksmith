"""Fail when a module or a public symbol has no docstring.

The codebase explains *why* rather than *what*, and that only works if every
entry point has somewhere to put the explanation. A public class with no
docstring is a missing paragraph, not a style nit: it is the thing a reader
hits first.

Private names are exempt. ``_parse_foo`` may be obvious from its body; a public
``resolve_app_prefixes`` cannot be.

Run with::

    python scripts/check_docstrings.py
"""

from __future__ import annotations

import ast
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PACKAGE = ROOT / "src" / "apksmith"


def public_nodes(tree: ast.Module):
    """Top-level classes and functions that callers can import, plus methods.

    Dunder methods are exempt: ``__init__`` on a dataclass is generated, and
    requiring a docstring on ``__post_init__`` would produce noise rather than
    clarity.
    """
    for node in tree.body:
        is_callable = isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
        if (is_callable or isinstance(node, ast.ClassDef)) and not node.name.startswith(
            "_"
        ):
            yield node.name, node
        if isinstance(node, ast.ClassDef):
            for child in node.body:
                if isinstance(
                    child, (ast.FunctionDef, ast.AsyncFunctionDef)
                ) and not child.name.startswith("_"):
                    yield f"{node.name}.{child.name}", child


def main() -> int:
    missing: list[str] = []
    modules = sorted(PACKAGE.rglob("*.py"))
    checked = 0

    for path in modules:
        relative = path.relative_to(ROOT).as_posix()
        tree = ast.parse(path.read_text(encoding="utf-8"))

        if not ast.get_docstring(tree):
            missing.append(f"{relative} (module)")

        for name, node in public_nodes(tree):
            checked += 1
            if not ast.get_docstring(node):
                missing.append(f"{relative}:{node.lineno} {name}")

    print(f"  {len(modules)} modules, {checked} public symbols checked")
    if missing:
        print(f"\n{len(missing)} public symbol(s) without a docstring:")
        for entry in missing:
            print(f"  - {entry}")
        return 1

    print("  every module and public symbol is documented")
    return 0


if __name__ == "__main__":
    sys.exit(main())
