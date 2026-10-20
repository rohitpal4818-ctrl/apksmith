"""
M5: the evaluation harness.

Without this, APKSmith is a tool that produces confident-sounding output of
unknown quality. With it, there is a number.

The problem with LLM evaluation is that "is this spec correct?" has no exact
answer, so most projects quietly avoid measuring. The approach here is
deliberately narrow and honest:

    Reference specs   Hand-written descriptions of a few well-known
                     open-source apps, from their public documentation --
                     not from the model being tested.

    Similarity metrics  Deterministic, explainable overlap measures between
                        the reference and what APKSmith produced.

We do not claim to measure truth. We measure *agreement with an independent
human description*, which is checkable, reproducible, and far more defensible
than a vibe check.

Every metric is a number someone could disagree with. That is the point: the
disagreement is visible.
"""

from __future__ import annotations

import json
import re
from collections.abc import Iterable
from dataclasses import dataclass, field
from pathlib import Path

from .understand.spec import BehaviourSpec

#: Words that carry no information about an app's behaviour. Removed before
#: comparing two descriptions, otherwise both texts score highly for sharing
#: the word "app".
_STOPWORDS = frozenset(
    [
        "a",
        "an",
        "the",
        "and",
        "or",
        "of",
        "to",
        "in",
        "for",
        "with",
        "that",
        "this",
        "it",
        "its",
        "is",
        "are",
        "was",
        "were",
        "be",
        "been",
        "app",
        "application",
        "user",
        "users",
        "can",
        "will",
        "may",
        "when",
        "where",
        "which",
        "one",
        "all",
        "any",
        "each",
        "other",
        "more",
        "most",
        "some",
        "such",
        "than",
        "then",
        "there",
        "these",
        "those",
        "very",
        "own",
        "same",
        "so",
    ]
)

_WORD = re.compile(r"[a-z0-9]+")


def _tokens(text: str) -> set[str]:
    return {w for w in _WORD.findall(text.lower()) if w not in _STOPWORDS and len(w) > 2}


def _norm_label(text: str) -> str:
    """Normalise a screen or feature name for fuzzy comparison.

    "Add Expense Screen" and "add_expense" should match; "Settings" and
    "Preferences" should not. Normalising to a token set handles the first
    without forcing the second.
    """
    return set(_WORD.findall(text.lower()))


# --------------------------------------------------------------------------- #
# Metrics
# --------------------------------------------------------------------------- #
@dataclass
class MetricResult:
    name: str
    value: float
    detail: str = ""

    @property
    def percent(self) -> float:
        return round(self.value * 100, 1)


def _prf(
    reference: Iterable[str], predicted: Iterable[str], normaliser
) -> dict[str, float]:
    """Precision, recall and F1 over a fuzzy label match.

    Two labels match when their normalised token sets intersect, which handles
    plural, ordering and formatting differences without a fuzzy-match library.
    """
    ref_items = [(r, normaliser(r)) for r in reference]
    pred_items = [(p, normaliser(p)) for p in predicted]

    matched_pred: set[int] = set()
    matched_ref: set[int] = set()

    for ri, (_, rnorm) in enumerate(ref_items):
        if not rnorm:
            continue
        for pi, (_, pnorm) in enumerate(pred_items):
            if pi in matched_pred or not pnorm:
                continue
            if rnorm & pnorm:
                matched_ref.add(ri)
                matched_pred.add(pi)
                break

    tp = len(matched_ref)
    precision = tp / len(pred_items) if pred_items else 0.0
    recall = tp / len(ref_items) if ref_items else 0.0
    f1 = (2 * precision * recall / (precision + recall)) if (precision + recall) else 0.0
    return {
        "precision": precision,
        "recall": recall,
        "f1": f1,
        "matched": tp,
        "reference_total": len(ref_items),
        "predicted_total": len(pred_items),
        "missed": [r for i, (r, _) in enumerate(ref_items) if i not in matched_ref],
        "spurious": [p for i, (p, _) in enumerate(pred_items) if i not in matched_pred],
    }


@dataclass
class CaseResult:
    """Evaluation of one app against its reference spec."""

    app: str
    metrics: list[MetricResult] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)

    @property
    def mean_f1(self) -> float:
        f1s = [m.value for m in self.metrics if m.name.endswith("_f1")]
        return sum(f1s) / len(f1s) if f1s else 0.0

    def to_dict(self) -> dict:
        return {
            "app": self.app,
            "mean_f1": round(self.mean_f1, 4),
            "metrics": [
                {"name": m.name, "value": round(m.value, 4), "detail": m.detail}
                for m in self.metrics
            ],
            "notes": self.notes,
        }


def evaluate(
    spec: BehaviourSpec, reference: dict, app_name: str | None = None
) -> CaseResult:
    """Score one generated spec against a hand-written reference.

    Parameters
    ----------
    spec
        What the pipeline produced.
    reference
        A dict with any of ``purpose``, ``screens``, ``features``,
        ``data_stored``, ``network_calls``. Each may be a list of strings or a
        list of dicts; only the label is used.
    app_name
        Used in the report. Defaults to the spec's own name.
    """
    result = CaseResult(app=app_name or spec.app_name or spec.package or "unknown")

    def _as_dict(item):
        """Accept both Pydantic models and plain dicts.

        A spec loaded from JSON arrives as models, but a spec built by hand in
        Python may carry raw dicts, and Pydantic does not re-validate on
        attribute assignment. Supporting both keeps the evaluator usable
        without forcing callers to round-trip through JSON.
        """
        if hasattr(item, "model_dump"):
            return item.model_dump()
        return item if isinstance(item, dict) else {"name": str(item)}

    def labels(raw) -> list[str]:
        out: list[str] = []
        for item in raw or []:
            data = _as_dict(item)
            if isinstance(data, dict):
                for key in ("name", "value", "endpoint", "purpose"):
                    if data.get(key):
                        out.append(str(data[key]))
                        break
            elif data:
                out.append(str(data))
        return out

    # -- screens -------------------------------------------------------- #
    ref_screens = labels(reference.get("screens"))
    if ref_screens:
        got = _prf(ref_screens, labels(spec.screens), _norm_label)
        result.metrics += [
            MetricResult("screens_precision", got["precision"]),
            MetricResult("screens_recall", got["recall"]),
            MetricResult("screens_f1", got["f1"]),
            MetricResult(
                "screens_matched",
                got["matched"] / len(ref_screens),
                f"{got['matched']}/{got['reference_total']}",
            ),
        ]
        if got["missed"]:
            result.notes.append(
                "Screens in reference but not found: " + ", ".join(got["missed"])
            )
        if got["spurious"]:
            result.notes.append(
                "Screens reported but not in reference: " + ", ".join(got["spurious"])
            )

    # -- features ------------------------------------------------------- #
    ref_features = labels(reference.get("features"))
    if ref_features:
        got = _prf(ref_features, labels(spec.features), _norm_label)
        result.metrics += [
            MetricResult("features_precision", got["precision"]),
            MetricResult("features_recall", got["recall"]),
            MetricResult("features_f1", got["f1"]),
        ]
        if got["missed"]:
            result.notes.append("Features missed: " + ", ".join(got["missed"]))

    # -- purpose -------------------------------------------------------- #
    ref_purpose = reference.get("purpose") or ""
    if ref_purpose:
        r, p = _tokens(ref_purpose), _tokens(spec.purpose or "")
        if r or p:
            overlap = len(r & p) / len(r) if r else 0.0
            result.metrics.append(
                MetricResult(
                    "purpose_token_overlap",
                    overlap,
                    "share of reference keywords present in the generated purpose",
                )
            )
            if not spec.purpose:
                result.notes.append("No purpose was produced.")

    # -- data ----------------------------------------------------------- #
    ref_data = labels(reference.get("data_stored"))
    if ref_data:
        got = _prf(ref_data, labels(spec.data_stored), _norm_label)
        result.metrics += [
            MetricResult("data_precision", got["precision"]),
            MetricResult("data_recall", got["recall"]),
            MetricResult("data_f1", got["f1"]),
        ]

    # -- network -------------------------------------------------------- #
    ref_net = labels(reference.get("network_calls"))
    if ref_net:
        got = _prf(ref_net, labels(spec.network_calls), _norm_label)
        result.metrics += [
            MetricResult("network_precision", got["precision"]),
            MetricResult("network_recall", got["recall"]),
            MetricResult("network_f1", got["f1"]),
        ]

    if not result.metrics:
        result.notes.append(
            "Reference contains nothing comparable. Add screens, features or a "
            "purpose to the reference to get a score."
        )
    return result


@dataclass
class SuiteReport:
    cases: list[CaseResult] = field(default_factory=list)

    @property
    def mean_f1(self) -> float:
        return sum(c.mean_f1 for c in self.cases) / len(self.cases) if self.cases else 0.0

    def per_metric(self) -> dict[str, float]:
        totals: dict[str, list[float]] = {}
        for case in self.cases:
            for m in case.metrics:
                totals.setdefault(m.name, []).append(m.value)
        return {k: sum(v) / len(v) for k, v in sorted(totals.items())}

    def to_markdown(self) -> str:
        lines = [
            "# APKSmith evaluation report",
            "",
            "Scores measure **agreement with an independent hand-written "
            "reference**, not truth. A high score means the pipeline found "
            "what a human reader of the documentation found. It does not mean "
            "the app is fully reconstructed.",
            "",
            "## Summary",
            "",
            f"- Cases: **{len(self.cases)}**",
            f"- Mean F1 across cases: **{self.mean_f1:.3f}**",
            "",
        ]

        if self.per_metric():
            lines += [
                "## Per-metric means",
                "",
                "| Metric | Mean |",
                "| --- | --- |",
            ]
            lines += [
                f"| {name} | {value:.3f} |" for name, value in self.per_metric().items()
            ]
            lines.append("")

        lines += [
            "## Per case",
            "",
            "| App | Mean F1 | Screens F1 | Features F1 | Purpose overlap |",
            "| --- | --- | --- | --- | --- |",
        ]
        for case in self.cases:
            lookup = {m.name: m.value for m in case.metrics}
            lines.append(
                f"| {case.app} | {case.mean_f1:.3f} "
                f"| {lookup.get('screens_f1', 0):.3f} "
                f"| {lookup.get('features_f1', 0):.3f} "
                f"| {lookup.get('purpose_token_overlap', 0):.3f} |"
            )
        lines.append("")

        notes = [(c.app, n) for c in self.cases for n in c.notes]
        if notes:
            lines += ["## Notes", ""]
            lines += [f"- **{app}** — {note}" for app, note in notes]
            lines.append("")

        lines += [
            "## How to read these numbers",
            "",
            "- `recall` low means the pipeline missed real behaviour.",
            "- `precision` low means it invented things. That is worse.",
            "- A low `purpose_token_overlap` with good screen F1 means the "
            "structure was found but the model could not summarise it.",
            "",
            "Three apps is a demonstration, not a benchmark. Treat the numbers "
            "as a regression signal: if a change makes them worse, that change "
            "is bad.",
        ]
        return "\n".join(lines) + "\n"


# --------------------------------------------------------------------------- #
# Reference data and loading
# --------------------------------------------------------------------------- #
def load_suite(path: Path) -> SuiteReport:
    """Load a reference suite from a JSON file.

    Expected shape::

        {
          "cases": [
            {
              "name": "F-Droid",
              "reference": {
                "purpose": "...",
                "screens": ["App list", "App detail"],
                "features": ["..."]
              }
            }
          ]
        }
    """
    data = json.loads(path.read_text(encoding="utf-8"))
    cases = data.get("cases", [])
    if not cases:
        raise ValueError(f"No cases found in {path}")

    return SuiteReport(
        cases=[
            evaluate(
                BehaviourSpec.model_validate(case["spec"]),
                case["reference"],
                app_name=case.get("name", "unnamed"),
            )
            for case in cases
            if case.get("spec")
        ]
    )


def save_suite(path: Path, suite: SuiteReport) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(suite.to_markdown(), encoding="utf-8")
