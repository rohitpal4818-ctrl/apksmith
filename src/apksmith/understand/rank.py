"""
Choosing which classes to send to the model.

You cannot send 11,949 files to a language model. You cannot send 990 either.
The job of this module is to pick the smallest set of classes that, between
them, describe what the app does.

The ranking is role-based rather than a black-box score, because a portfolio
tool should be able to explain its own decisions:

    screen      Activities and Fragments. One of these is usually one screen.
    entrypoint  The Application subclass. Says how the app starts.
    data        Network, database and repository classes.
    model       Data classes. Say what the app's data looks like.
    integration Third-party SDK wrappers the app actually calls.
    other       Everything else. Sent only if there is budget left.

Within a role, classes are ordered by how much they say: more recognised
methods and more meaningful string literals wins.
"""

from __future__ import annotations

import re

from .extract import ClassSummary

#: Roles, highest value first.
ROLE_ORDER = ["screen", "entrypoint", "data", "model", "integration", "other"]

#: Class-name signals for each role.
_SCREEN_NAMES = re.compile(
    r"(Activity|Fragment|Screen|Page|Dialog|BottomSheet|ViewPager|Compose)", re.IGNORECASE
)
_ENTRYPOINT_NAMES = re.compile(r"^(Application|App|.*Application)$")
_DATA_NAMES = re.compile(
    r"(Api|Service|Client|Repository|Repo|Network|Remote|DataSource|Store|"
    r"Dao|Database|Manager|Fetcher|Loader|Provider|Worker)",
    re.IGNORECASE,
)
_MODEL_NAMES = re.compile(
    r"(Model|Entity|Response|Request|Result|Dto|DTO|Item|Entry|Bean|Pojo)", re.IGNORECASE
)
_INTEGRATION_NAMES = re.compile(
    r"(Firebase|Analytics|Crash|Sentry|Auth|Payment|Billing|Social|Share|"
    r"Notification|Push|Advertising|Ad|Map|Location|Camera|Media)",
    re.IGNORECASE,
)

#: Methods that strongly indicate a user-facing screen.
_SCREEN_METHODS = re.compile(
    r"(onCreate|onResume|onStart|setContentView|inflate|compose|Composable|"
    r"onClick|onSubmit|setup|init)",
    re.IGNORECASE,
)

#: Methods that indicate data or network work.
_DATA_METHODS = re.compile(
    r"(fetch|load|get|post|put|delete|request|query|insert|save|store|upload|"
    r"download|parse|serialize|deserialize|execute|enqueue|read|write)",
    re.IGNORECASE,
)

#: Strings that look like real content rather than compiler plumbing.
_MEANINGFUL_STRING = re.compile(r"^[A-Za-z][\w .,!?\-:/%@#'\"() ]{2,60}$")


def classify(summary: ClassSummary) -> str:
    """Assign a class to a role."""
    name = summary.name

    # Inner and anonymous classes rarely describe a screen on their own.
    is_top_level = "Anonymous" not in name and not re.match(r".*\$\d+$", name)

    if _ENTRYPOINT_NAMES.match(name) and is_top_level:
        return "entrypoint"

    if _SCREEN_NAMES.search(name) and is_top_level:
        return "screen"

    if _INTEGRATION_NAMES.search(name) and _DATA_METHODS.search(
        " ".join(summary.methods)
    ):
        return "integration"

    if _DATA_NAMES.search(name):
        return "data"

    if _MODEL_NAMES.search(name):
        return "model"

    if _SCREEN_METHODS.search(" ".join(summary.methods)) and is_top_level:
        return "screen"

    return "other"


def _content_score(summary: ClassSummary) -> float:
    """How much does this class actually say about behaviour?"""
    score = 0.0

    methods = summary.methods
    screen_methods = sum(1 for m in methods if _SCREEN_METHODS.search(m))
    data_methods = sum(1 for m in methods if _DATA_METHODS.search(m))
    score += min(screen_methods, 6) * 2.0
    score += min(data_methods, 6) * 1.5

    meaningful = sum(
        1 for s in summary.strings if _MEANINGFUL_STRING.match(s)
    )
    score += min(meaningful, 8) * 1.0

    # A body means we can say what happens, not just what exists.
    if summary.body_snippet:
        score += 3.0
    score += min(len(summary.body_snippet) / 400.0, 4.0)

    if summary.superclass:
        score += 1.0

    # Prefer classes with a reasonable name over ones the obfuscator mangled.
    if len(summary.name) <= 2:
        score *= 0.2
    elif len(summary.name) <= 3:
        score *= 0.6

    # Boilerplate Hilt/Dagger/Kotlin plumbing describes the framework, not the app.
    if re.match(r"^(Hilt_|Dagger|_?[A-Z]{1,3}Factory|_?[A-Z]{1,3}Module)$", summary.name):
        score *= 0.15

    return score


def rank(summaries: list[ClassSummary]) -> list[ClassSummary]:
    """Score, role-tag and sort. Highest value first."""
    for s in summaries:
        s.role = classify(s)
        s.score = _content_score(s)

    weight = {role: float(len(ROLE_ORDER) - i) for i, role in enumerate(ROLE_ORDER)}
    for s in summaries:
        # Role dominates; content score only breaks ties within a role.
        s.score = s.score * weight.get(s.role, 0.5) + weight.get(s.role, 0.5)

    return sorted(summaries, key=lambda s: -s.score)


def select(
    summaries: list[ClassSummary],
    max_classes: int = 60,
    per_role_cap: int | None = None,
) -> list[ClassSummary]:
    """Pick the classes worth sending to the model.

    Parameters
    ----------
    summaries
        Output of :func:`rank`.
    max_classes
        Total budget. 60 classes at roughly 800 characters each is about
        48k characters, which comfortably fits a large context window once
        the prompt is added.
    per_role_cap
        Stop taking more than this many from any single role. Without it, a
        Compose-based app with 40 screens would consume the whole budget on
        screens and the model would never see the data layer.
    """
    ranked = rank(summaries)

    by_role: dict[str, list[ClassSummary]] = {}
    for s in ranked:
        by_role.setdefault(s.role, []).append(s)

    cap = per_role_cap if per_role_cap else max_classes

    selected: list[ClassSummary] = []
    # Walk roles in priority order, round-robin, so every role gets covered
    # before any single role is exhausted.
    exhausted = False
    while len(selected) < max_classes and not exhausted:
        exhausted = True
        for role in ROLE_ORDER:
            if len(selected) >= max_classes:
                break
            items = by_role.get(role) or []
            used = sum(1 for s in selected if s.role == role)
            if used < min(cap, len(items)):
                selected.append(items[used])
                exhausted = False

    return selected


def role_census(summaries: list[ClassSummary]) -> dict[str, int]:
    """How many classes fall into each role.

    Ranks first, so calling this on freshly extracted summaries is safe. Doing
    it the other way round silently reports every class as "other", because
    `role` is not populated until `rank()` runs.
    """
    rank(summaries)
    counts: dict[str, int] = {}
    for s in summaries:
        counts[s.role] = counts.get(s.role, 0) + 1
    return dict(sorted(counts.items(), key=lambda kv: -kv[1]))