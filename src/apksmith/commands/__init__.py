"""Command groups mounted onto the root ``apksmith`` CLI.

Each module owns one verb group and its options. None of them contain pipeline
logic: they validate input, call a function from ``apksmith.app`` or
``apksmith.understand``, and format the result. Keeping that boundary sharp is
what makes the commands readable and the pipeline testable without Typer.

    understand   APK -> behaviour spec        (needs a model)
    generate     behaviour spec -> project    (deterministic)
    evaluate     spec vs references           (deterministic)

The M1 commands (``scan``, ``coverage``, ``version``) are small enough to live
directly in ``apksmith.cli``.
"""

from . import evaluate, generate, understand

__all__ = ["evaluate", "generate", "understand"]
