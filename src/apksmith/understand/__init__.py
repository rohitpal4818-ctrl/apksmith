"""M2: the understanding stage.

    extract    decompiled Java -> clean, LLM-readable ClassSummary objects
    rank       choose which classes actually describe the app
    llm        OpenRouter client with caching and rate-limit reporting
    prompt     prompt construction and the JSON contract
    spec       the BehaviourSpec output model
    pipeline   chunk, extract, merge, synthesise
"""

from __future__ import annotations

from .extract import ClassSummary, extract_tree, summarise_class
from .llm import (
    DEFAULT_MODEL,
    LlmClient,
    LlmStats,
    known_providers,
    parse_json_loose,
)
from .pipeline import UnderstandResult, understand
from .rank import classify, rank, role_census, select
from .spec import (
    BehaviourSpec,
    DataSpec,
    FeatureSpec,
    NetworkSpec,
    PartialSpec,
    ScreenSpec,
)

__all__ = [
    "BehaviourSpec",
    "ClassSummary",
    "DataSpec",
    "DEFAULT_MODEL",
    "FeatureSpec",
    "LlmClient",
    "LlmStats",
    "NetworkSpec",
    "PartialSpec",
    "ScreenSpec",
    "UnderstandResult",
    "classify",
    "extract_tree",
    "known_providers",
    "parse_json_loose",
    "rank",
    "role_census",
    "select",
    "summarise_class",
    "understand",
]