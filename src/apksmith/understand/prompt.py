"""
Prompt construction.

The prompt is the actual product here. A decompiled Android class is hard for
a model to reason about: it is full of framework calls, the class names have
been through a decompiler, and there is no way to see the UI. So the prompt
has to do three jobs:

1. Tell the model what kind of thing it is looking at, and what to ignore.
2. Ask for JSON with a fixed shape, because free models drift without one.
3. Demand evidence, so the output can be checked rather than trusted.

We ask for evidence because hallucination is the main failure mode of this
whole approach. A spec that names classes it was not shown is worthless. A
spec that cites the classes it based each screen on can be verified in seconds.
"""

from __future__ import annotations

from ..models import RiskReport
from .extract import ClassSummary

SYSTEM = """\
You are a senior Android engineer performing behavioural reverse engineering.

You are given decompiled Java classes from an Android app. Your job is to
describe what the app DOES, so that a different engineer could rebuild it.

Rules you must follow:

1. Report only what the code supports. Do not invent screens, features or API
   calls that are not evidenced by the class summaries you are shown.
2. Every screen must cite the class names it was inferred from, in "evidence".
3. The decompiled code is noisy. IGNORE all of the following, they carry no
   information about the app:
   - Kotlin/Java compiler plumbing (Intrinsics, Continuation, Function0, Coroutine)
   - Dependency injection scaffolding (Hilt_*, Dagger*, _*Factory, _*Module)
   - Synthetic lambda and outline classes ($$ExternalSynthetic, $$Lambda)
   - Getter/setter pairs that only return a stored field
4. Describe behaviour, not implementation. Say "shows a list of apps with an
   install button", not "uses a RecyclerView with an adapter".
5. If you cannot determine something, leave it out. Do not guess.
6. You will be given ONE part of an app at a time. Do not try to describe the
   whole app. Describe what these particular classes do.
7. Respond with JSON only. No prose before or after. No markdown fences.

The exact JSON shape you must return:

{
  "purpose_hint": "one sentence on what this part of the app does",
  "screens": [
    {
      "name": "short human name like 'App list'",
      "purpose": "what the user does on this screen",
      "shows": ["element the user sees"],
      "actions": ["thing the user can do here"],
      "evidence": ["exact class names this was read from"],
      "confidence": "high | medium | low"
    }
  ],
  "features": [
    {"name": "feature name", "description": "what it does", "implemented": true}
  ],
  "data_stored": [
    {"name": "what is stored", "kind": "preferences|database|file|cache",
     "description": "what it holds"}
  ],
  "network_calls": [
    {"purpose": "why the app makes this request", "endpoint": "URL or path",
     "method": "GET|POST|unknown", "evidence": ["class or string that shows it"]}
  ],
  "platform_dependencies": ["something the app needs from the OS or hardware"],
  "caveats": ["what you could not determine"]
}

Return every list, even if empty. An empty list is a valid and useful answer.
"""

SYNTHESIS_SYSTEM = """\
You are merging several partial behavioural descriptions of one Android app
into a single coherent specification.

The partials each describe a different part of the same app, extracted
separately. They will overlap, disagree in naming, and some will be wrong.

Produce one specification that:

1. States the app's actual purpose in one or two sentences, for a specific
   audience of users.
2. Merges duplicate screens. If three partials describe "app list", "apps",
   and "application list", that is ONE screen called "App list".
3. Keeps features that are corroborated. A feature seen in only one partial,
   with no evidence, should be dropped or marked as uncertain in "caveats".
4. Orders screens the way a user would encounter them.
5. Explains each permission the app declared, in terms of observed behaviour.

Respond with JSON only, no prose, no markdown fences. Shape:

{
  "app_name": "human name",
  "package": "package name",
  "purpose": "one or two sentences",
  "target_users": "who this is for",
  "screens": [
    {"name": "", "purpose": "", "shows": [], "actions": [],
     "evidence": [], "confidence": "high|medium|low"}
  ],
  "features": [{"name": "", "description": "", "implemented": true}],
  "data_stored": [{"name": "", "kind": "", "description": ""}],
  "network_calls": [{"purpose": "", "endpoint": "", "method": "", "evidence": []}],
  "permissions_justified": {"android.permission.X": "why, from observed behaviour"},
  "platform_dependencies": [],
  "caveats": ["anything uncertain or unobservable from static analysis"]
}
"""


def render_classes(summaries: list[ClassSummary]) -> str:
    """Render selected classes as the user message."""
    parts: list[str] = []
    for s in summaries:
        parts.append(f"[{s.role}]")
        parts.append(s.to_prompt_block())
    return "\n\n".join(parts)


def render_static_facts(report: RiskReport) -> str:
    """Condense the M1 report into the few facts worth giving the model.

    Endpoints, permissions and SDK names are ground truth from the binary. The
    model does not need to rediscover them, and telling it up front means the
    final spec can cross-reference them instead of guessing.
    """
    lines: list[str] = ["## Static analysis facts (ground truth, from the binary)"]
    i = report.identity

    lines.append(f"Package: {i.package}")
    if i.app_name:
        lines.append(f"App name: {i.app_name}")
    if i.version_name:
        lines.append(f"Version: {i.version_name}")

    if report.sdks:
        names = ", ".join(s.name for s in report.sdks[:15])
        lines.append(f"Third-party SDKs detected: {names}")

    risky = [p for p in report.permissions if p.severity.weight >= 15]
    if risky:
        lines.append("\nNotable permissions declared:")
        for p in risky[:15]:
            lines.append(f"- {p.name}")

    if report.endpoints:
        lines.append("\nEndpoints found in strings:")
        for e in report.endpoints[:20]:
            lines.append(f"- {e.value}")

    if report.components:
        activities = [c.name for c in report.components if c.kind == "activity"]
        if activities:
            lines.append(f"\nDeclared activities ({len(activities)}):")
            lines.append(", ".join(a.rsplit('.', 1)[-1] for a in activities[:25]))

    services = [c.name for c in report.components if c.kind == "service"]
    if services:
        lines.append(f"\nDeclared services ({len(services)}):")
        lines.append(", ".join(s.rsplit('.', 1)[-1] for s in services[:15]))

    return "\n".join(lines)


def extraction_prompt(
    summaries: list[ClassSummary],
    report: RiskReport,
    part_index: int,
    part_total: int,
) -> str:
    """User message for one extraction pass."""
    facts = render_static_facts(report)
    code = render_classes(summaries)
    return (
        f"## Part {part_index} of {part_total}\n\n"
        f"{facts}\n\n"
        f"## Decompiled classes for this part\n\n"
        f"{code}\n\n"
        f"Describe what these {len(summaries)} classes do, following the JSON "
        f"shape in your instructions. Return JSON only."
    )


def synthesis_prompt(
    partials_json: str,
    report: RiskReport,
) -> str:
    """User message for the final merge pass."""
    facts = render_static_facts(report)
    return (
        f"{facts}\n\n"
        f"## Partial descriptions of this app\n\n"
        f"{partials_json}\n\n"
        f"Merge these into one coherent specification following the JSON shape "
        f"in your instructions. Return JSON only."
    )


def repair_prompt(bad_output: str, error: str) -> str:
    """Ask the model to fix its own malformed JSON.

    Free models emit trailing commas and stray prose often enough that a single
    retry is usually enough. This is cheaper and more reliable than demanding
    perfection on the first attempt.
    """
    return (
        "Your previous response could not be parsed as JSON.\n"
        f"Error: {error}\n\n"
        f"Response was:\n{bad_output[:1200]}\n\n"
        "Return the same information as valid JSON only. No markdown fences, "
        "no commentary, no trailing commas."
    )