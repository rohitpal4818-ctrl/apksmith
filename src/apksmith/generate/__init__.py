"""
M3: code generation.

BehaviourSpec -> a runnable Flutter project.

    naming     identifier derivation from arbitrary labels
    templates  Dart/Flutter templates
    flutter    the project builder

The builder is pure code with no model dependency, so the output compiles even
with no API key. See :mod:`apksmith.generate.flutter` for why that split is
deliberate.
"""

from __future__ import annotations

from .flutter import build_flutter_project
from .naming import GeneratedFile, GenerationResult, pascal, singular, snake

__all__ = [
    "GeneratedFile",
    "GenerationResult",
    "build_flutter_project",
    "pascal",
    "singular",
    "snake",
]