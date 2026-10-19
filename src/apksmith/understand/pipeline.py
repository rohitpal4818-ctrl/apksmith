"""
The M2 pipeline: decompiled sources + M1 report -> BehaviourSpec.

Two passes, because a single pass over 60 classes produces a shallow guess and
a single pass over 900 is impossible:

    Pass 1  chunk   Selected classes are grouped into batches sized to fit a
                    context window. Each batch is analysed independently.
    Pass 2  merge   The partial results are merged into one specification,
                    de-duplicated and cross-checked against the static facts.

The chunking is where the quality comes from. A batch is never allowed to be
dominated by one role: mixing screens with data classes in the same batch
gives the model enough context to connect the two, which is what makes the
extraction useful rather than a class listing.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from pydantic import ValidationError

from ..errors import ApkSmithError
from ..models import RiskReport
from .extract import ClassSummary, extract_tree
from .llm import LlmClient, LlmStats, parse_json_loose
from .prompt import (
    SYNTHESIS_SYSTEM,
    SYSTEM,
    extraction_prompt,
    repair_prompt,
    synthesis_prompt,
)
from .rank import rank, role_census, select
from .spec import BehaviourSpec, PartialSpec


class UnderstandingFailed(ApkSmithError):
    """The model could not produce a usable specification."""


@dataclass
class UnderstandResult:
    """Everything one run produced, including its own diagnostics."""

    spec: BehaviourSpec
    stats: LlmStats
    classes_considered: int = 0
    classes_sent: int = 0
    parts: int = 0
    role_census: dict[str, int] = field(default_factory=dict)
    cache_dir: Path | None = None


def resolve_app_prefixes(
    report: RiskReport,
    root: Path,
    min_classes: int = 20,
) -> list[str]:
    """Work out which source directories hold the app's *own* code.

    The obvious approach -- filter on the manifest package name -- is wrong far
    more often than it is right. F-Droid declares ``org.fdroid.fdroid`` but its
    classes live under ``org/fdroid/``. Plenty of apps have a version or
    flavour segment in the package that never appears in the source tree.
    Getting this wrong silently reduces the analysis to a handful of classes,
    which looks like "this app is trivial" rather than like a bug.

    So we derive candidates from the manifest's component class names, which
    name real classes and therefore real packages, then measure which prefix
    actually captures the most source. Component packages are app-specific by
    construction, so a top-level prefix like ``org`` only gets chosen if the
    app genuinely lives there.

    Returns the winning prefix, or an empty list when nothing matched.
    """
    base = root / "sources" if (root / "sources").is_dir() else root
    if not base.is_dir():
        return []

    # Namespaces owned by libraries, never by the app being analysed. A library
    # can still inject components into the manifest -- Room registers a
    # service, ProfileInstaller registers a receiver -- so these appear in the
    # component list and would otherwise be mistaken for app code.
    library_namespaces = (
        "androidx.", "android.", "com.google.", "com.android.", "kotlin.",
        "kotlinx.", "com.squareup.", "dagger.", "javax.", "java.", "sun.",
        "org.jetbrains.", "org.json.", "org.apache.",
    )

    def owned(package: str) -> bool:
        return not package.startswith(library_namespaces)

    # One pass over the tree so the counting below is pure arithmetic.
    paths = [p.relative_to(base).as_posix() for p in base.rglob("*.java")]

    def file_count(prefix: str) -> int:
        return sum(1 for p in paths if p.startswith(prefix + "/"))

    def covers(prefix: str, fqcn: str | None) -> bool:
        if not fqcn:
            return False
        dotted = prefix.replace("/", ".")
        return fqcn == dotted or fqcn.startswith(dotted + ".")

    # The manifest package, trimmed from the most specific candidate down. Each
    # step is tried before widening, so the narrowest prefix that still covers
    # the app's entry point wins.
    #
    # The manifest package is not always a source prefix: F-Droid declares
    # ``org.fdroid.fdroid`` but ships its code under ``org/fdroid/``. Trimming
    # one segment handles that, and keeps the result inside the app's own
    # subtree instead of wandering up to a shared parent such as ``org/`` --
    # which would pull in org/jetbrains and org/json.
    entry_point = report.identity.main_activity
    candidates: list[str] = []

    if report.identity.package:
        parts = [p for p in report.identity.package.split(".") if p]
        for i in range(len(parts), 0, -1):
            candidates.append("/".join(parts[:i]))

    # The entry point's own package, which is by definition app code.
    if entry_point and "." in entry_point:
        entry_parts = [p for p in entry_point.rsplit(".", 1)[0].split(".") if p]
        for i in range(len(entry_parts), 0, -1):
            candidates.append("/".join(entry_parts[:i]))

    for candidate in candidates:
        if covers(candidate, entry_point) and file_count(candidate) >= min_classes:
            return [candidate]

    # No candidate covers the entry point. Take the first with real code.
    for candidate in candidates:
        if file_count(candidate) >= min_classes:
            return [candidate]

    return candidates[:1]


def _chunk(
    summaries: list[ClassSummary], per_chunk: int
) -> list[list[ClassSummary]]:
    """Split selected classes into chunks, interleaving roles.

    Selected classes arrive sorted by score, so a naive split would put every
    screen in chunk 1 and every data class in chunk 2. Interleaving by stride
    puts one of each role in every chunk, which is what gives each pass enough
    context to describe something real.
    """
    if per_chunk <= 0:
        per_chunk = 12

    buckets: dict[str, list[ClassSummary]] = {}
    for s in summaries:
        buckets.setdefault(s.role, []).append(s)

    roles = list(buckets)
    chunks: list[list[ClassSummary]] = []
    current: list[ClassSummary] = []
    cursors = dict.fromkeys(roles, 0)
    exhausted = False

    while not exhausted and len(chunks) < 1000:
        exhausted = True
        for role in roles:
            if len(current) >= per_chunk:
                break
            items = buckets[role]
            idx = cursors[role]
            if idx < len(items):
                current.append(items[idx])
                cursors[role] += 1
                exhausted = False
        if current:
            chunks.append(current)
            current = []

    return chunks


def _ask_json(
    client: LlmClient,
    system: str,
    user: str,
    *,
    max_tokens: int,
    attempts: int = 2,
) -> dict:
    """One logical model call that tolerates malformed JSON.

    Returns the parsed dict, or raises UnderstandingFailed. Never returns a
    half-parsed structure: a wrong spec is worse than no spec, because M3
    would generate code from it.
    """
    last_error = "no response"
    last_output = ""

    for attempt in range(attempts):
        text = client.complete(
            system=system,
            user=user if attempt == 0 else repair_prompt(last_output, last_error),
            max_tokens=max_tokens,
        )
        last_output = text
        parsed = parse_json_loose(text)
        if parsed is not None:
            return parsed
        last_error = "response was not valid JSON"

    raise UnderstandingFailed(
        f"Model did not return valid JSON after {attempts} attempts. "
        f"Last output began: {last_output[:200]!r}"
    )


def understand(
    report: RiskReport,
    decompiled_root: Path,
    client: LlmClient,
    *,
    package_prefixes: list[str] | None = None,
    max_classes: int = 60,
    per_chunk: int = 12,
    per_role_cap: int = 20,
    verbose: bool = False,
) -> UnderstandResult:
    """Run the full M2 pipeline and return a BehaviourSpec.

    Parameters
    ----------
    report
        The M1 RiskReport. Its endpoints, permissions and component list are
        fed to the model as ground truth.
    decompiled_root
        Directory jadx wrote to. Must contain ``sources/``.
    client
        Configured LlmClient.
    package_prefixes
        Which packages are the app's own code. Defaults to the package from
        the report.
    max_classes
        Total class budget across all chunks.
    per_chunk
        Classes per model call. Each class averages roughly 800 characters,
        so 12 is about 10k characters -- comfortable, and small enough that
        the model attends to each class.
    """
    prefixes = package_prefixes or resolve_app_prefixes(report, decompiled_root)

    def say(msg: str) -> None:
        if verbose:
            print(f"  [m2] {msg}")

    say(f"extracting summaries from {decompiled_root}")
    summaries = extract_tree(decompiled_root, package_prefixes=prefixes)
    say(f"  {len(summaries):,} classes in the app's own package")

    # Rank before taking the census. `role_census` reads `ClassSummary.role`,
    # which only `rank()` populates, so taking it first made the diagnostic
    # report {'other': N} for every app regardless of content -- actively
    # misleading when you are trying to work out why a run looks wrong.
    rank(summaries)
    census = role_census(summaries)
    selected = select(summaries, max_classes=max_classes, per_role_cap=per_role_cap)
    say(f"selected {len(selected)} for analysis; roles: {census}")

    chunks = _chunk(selected, per_chunk)
    say(f"split into {len(chunks)} chunks")

    partials: list[PartialSpec] = []
    for idx, batch in enumerate(chunks, start=1):
        say(f"chunk {idx}/{len(chunks)} ({len(batch)} classes)")
        user = extraction_prompt(batch, report, idx, len(chunks))
        raw = _ask_json(client, SYSTEM, user, max_tokens=4096)
        try:
            partials.append(PartialSpec.model_validate(raw))
        except ValidationError as exc:
            say(f"  chunk {idx} failed validation, skipped: {exc.error_count()} issues")

    if not partials:
        raise UnderstandingFailed(
            "No chunk produced a valid partial specification. Check the model "
            "id is still on the free tier, or try a larger model."
        )

    say(f"synthesising {len(partials)} partials")
    merged = _merge_partials(partials)
    synthesis_input = merged.model_dump_json(indent=2)
    raw_final = _ask_json(
        client,
        SYNTHESIS_SYSTEM,
        synthesis_prompt(synthesis_input, report),
        max_tokens=8192,
    )

    payload = dict(raw_final)
    payload.setdefault("package", report.identity.package)
    payload.setdefault("app_name", report.identity.app_name or "")
    # The static report is ground truth; a model should not contradict it.
    payload["package"] = report.identity.package

    try:
        spec = BehaviourSpec.model_validate(payload)
    except ValidationError as exc:
        say(f"final spec failed validation ({exc.error_count()} issues); using merged partials")
        spec = _fallback_spec(report, partials)

    return UnderstandResult(
        spec=spec,
        stats=client.stats,
        classes_considered=len(summaries),
        classes_sent=len(selected),
        parts=len(chunks),
        role_census=census,
        cache_dir=client.cache_dir,
    )


def _merge_partials(partials: list[PartialSpec]) -> PartialSpec:
    """De-duplicate partial results before synthesis.

    Doing this in code rather than asking the model to do it saves a
    significant amount of input tokens, and de-duplication is exactly the kind
    of mechanical work a model does unreliably.
    """
    merged = PartialSpec()
    seen_screens: set[str] = set()
    seen_features: set[str] = set()
    seen_data: set[str] = set()
    seen_net: set[str] = set()

    for p in partials:
        merged.purpose_hint = merged.purpose_hint or p.purpose_hint
        merged.platform_dependencies.extend(p.platform_dependencies)
        merged.caveats.extend(p.caveats)

        for s in p.screens:
            key = s.name.strip().lower()
            if key and key not in seen_screens:
                seen_screens.add(key)
                merged.screens.append(s)

        for f in p.features:
            key = f.name.strip().lower()
            if key and key not in seen_features:
                seen_features.add(key)
                merged.features.append(f)

        for d in p.data_stored:
            key = d.name.strip().lower()
            if key and key not in seen_data:
                seen_data.add(key)
                merged.data_stored.append(d)

        for n in p.network_calls:
            key = (n.endpoint or n.purpose or "").strip().lower()
            if key and key not in seen_net:
                seen_net.add(key)
                merged.network_calls.append(n)

    merged.platform_dependencies = sorted(set(merged.platform_dependencies))
    merged.caveats = sorted(set(merged.caveats))
    return merged


def _fallback_spec(report: RiskReport, partials: list[PartialSpec]) -> BehaviourSpec:
    """Build a spec from partials when the synthesis output is unusable.

    Degraded but honest: we return what the chunks found rather than failing
    outright, and record the limitation in caveats so nobody mistakes this for
    a complete understanding.
    """
    merged = _merge_partials(partials)
    return BehaviourSpec(
        app_name=report.identity.app_name or "",
        package=report.identity.package,
        purpose=merged.purpose_hint or "Could not be determined.",
        screens=merged.screens,
        features=merged.features,
        data_stored=merged.data_stored,
        network_calls=merged.network_calls,
        platform_dependencies=merged.platform_dependencies,
        caveats=list(merged.caveats)
        + [
            "Synthesis pass failed validation. This specification is a direct "
            "merge of partial results and has not been de-duplicated by role "
            "or reconciled against each other."
        ],
    )
