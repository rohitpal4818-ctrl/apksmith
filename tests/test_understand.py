"""
Tests for the M2 understanding layer.

These cover the parts that do not need an API key: source filtering, class
ranking, chunk interleaving, JSON salvage, and the behaviour-spec contract.
Anything that needs a network call is tested through a stub client instead, so
the suite never spends rate-limit budget.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from apksmith.models import AppIdentity, Component, RiskReport
from apksmith.understand.extract import ClassSummary, summarise_class
from apksmith.understand.llm import parse_json_loose
from apksmith.understand.pipeline import _chunk, _merge_partials, resolve_app_prefixes
from apksmith.understand.prompt import render_static_facts
from apksmith.understand.rank import classify, rank, select
from apksmith.understand.spec import BehaviourSpec, PartialSpec

ROOT = Path(__file__).resolve().parents[1]


# --------------------------------------------------------------------------- #
# Extraction
# --------------------------------------------------------------------------- #
KOTLIN_JUNK = """\
package org.example;

import kotlin.jvm.internal.Intrinsics;
import androidx.compose.runtime.Composer;

@Metadata(d1 = {"\\u0000\\u0000\\u0000garbage"}, d2 = {"more", "garbage"})
public final class LoginActivity extends Hilt_LoginActivity {
    private final Repository repo;
    public static final String TAG = "login";

    public LoginActivity() {
        this.repo = null;
    }

    public void onCreate(Bundle b) {
        this.repo.load();
        Log.d("LoginActivity", "started");
    }
}
"""


def test_extraction_strips_metadata_blob(tmp_path: Path):
    f = tmp_path / "LoginActivity.java"
    f.write_text(KOTLIN_JUNK, encoding="utf-8")

    s = summarise_class(f)
    assert s is not None
    assert s.name == "LoginActivity"  # not the whole declaration line
    assert s.superclass == "Hilt_LoginActivity"
    assert "repo" in s.fields
    assert "onCreate" in " ".join(s.methods)

    block = s.to_prompt_block()
    assert "garbage" not in block, "@Metadata blob should be stripped"
    assert "Intrinsics" not in block, "compiler plumbing should be filtered"


def test_extraction_rejects_synthetic_classes(tmp_path: Path):
    f = tmp_path / "MainActivity$$ExternalSyntheticLambda1.java"
    f.write_text(
        "package org.example;\n"
        "public final class MainActivity$$ExternalSyntheticLambda1 {\n"
        "    public void invoke(Object o) { helper(); }\n"
        "}\n",
        encoding="utf-8",
    )
    assert summarise_class(f) is None


def test_extraction_skips_empty_classes(tmp_path: Path):
    f = tmp_path / "Empty.java"
    f.write_text("package a;\npublic class Empty {\n}\n", encoding="utf-8")
    assert summarise_class(f) is None


def test_extraction_survives_undecodable_bytes(tmp_path: Path):
    """A class with real content must still parse when bytes are invalid."""
    f = tmp_path / "Weird.java"
    f.write_bytes(
        b"package a;\n"
        b'public class Weird { private String label = "\xff\xfe";\n'
        b"    public void refresh(String url) { label = url; } }\n"
    )
    s = summarise_class(f)
    assert s is not None, "invalid bytes must not discard a real class"
    assert s.name == "Weird"
    assert "refresh" in " ".join(s.methods)


def test_extraction_drops_class_with_nothing_to_say(tmp_path: Path):
    """A class with no methods, fields or strings is not worth sending."""
    f = tmp_path / "Empty.java"
    f.write_bytes(b"package a;\npublic class Empty {\xff\xfe }\n")
    assert summarise_class(f) is None


def test_class_summary_block_is_bounded():
    s = ClassSummary(
        fqcn="a.B",
        package="a",
        name="B",
        fields=[f"f{i}" for i in range(50)],
        methods=[f"m{i}" for i in range(50)],
        strings=[f"s{i}" for i in range(50)],
        body_snippet="\n".join(f"line {i}" for i in range(100)),
    )
    block = s.to_prompt_block()
    assert len(block) < 4000, "a single class must not blow the context window"


# --------------------------------------------------------------------------- #
# Ranking
# --------------------------------------------------------------------------- #
def _summary(name: str, methods=(), strings=()) -> ClassSummary:
    return ClassSummary(
        fqcn=f"com.example.{name}",
        package="com.example",
        name=name,
        methods=list(methods),
        strings=list(strings),
    )


def test_activity_is_classified_as_screen():
    assert classify(_summary("LoginActivity", ["onCreate", "setContentView"])) == "screen"


def test_repository_is_classified_as_data():
    assert classify(_summary("UserRepository", ["fetch", "load"])) == "data"


def test_response_model_is_classified_as_model():
    assert classify(_summary("UserResponse", [])) == "model"


def test_select_respects_per_role_cap():
    summaries = [_summary(f"Screen{i}") for i in range(30)]
    summaries += [_summary(f"Repo{i}", ["fetch"]) for i in range(30)]
    selected = select(summaries, max_classes=40, per_role_cap=10)
    screens = sum(1 for s in selected if s.role == "screen")
    assert screens <= 10, "one role must not consume the whole budget"


def test_select_covers_every_role():
    summaries = [_summary("LoginActivity", ["onCreate"])]
    summaries += [_summary("UserRepository", ["fetch"])]
    summaries += [_summary("UserResponse")]
    selected = select(summaries, max_classes=10)
    roles = {s.role for s in selected}
    assert {"screen", "data", "model"} <= roles


def test_select_respects_max_classes():
    summaries = [_summary(f"Screen{i}", ["onCreate"]) for i in range(100)]
    assert len(select(summaries, max_classes=20)) <= 20


# --------------------------------------------------------------------------- #
# Chunking
# --------------------------------------------------------------------------- #
def test_chunks_do_not_group_one_role_together():
    summaries = [_summary(f"Screen{i}", ["onCreate"]) for i in range(20)]
    summaries += [_summary(f"Repo{i}", ["fetch"]) for i in range(20)]
    # rank() is what assigns roles in the real pipeline.
    chunks = _chunk(rank(summaries), per_chunk=8)
    assert len(chunks) >= 4
    # Every chunk should contain more than one role, so the model has context.
    for chunk in chunks[:-1]:
        assert len({s.role for s in chunk}) >= 2, "chunk was role-homogeneous"


def test_chunking_respects_size():
    summaries = [_summary(f"C{i}") for i in range(30)]
    for chunk in _chunk(summaries, per_chunk=10):
        assert len(chunk) <= 10


# --------------------------------------------------------------------------- #
# JSON salvage
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize(
    "raw",
    [
        '{"a": 1}',
        'Here you go:\n```json\n{"a": 1}\n```\nHope that helps!',
        '```\n{"a": 1}\n```',
        'text before {"a": 1} text after',
        '{"a": 1,}',
        '  {"a": {"b": [1, 2,]}}  ',
    ],
)
def test_parse_json_loose_salvages_awkward_output(raw):
    parsed = parse_json_loose(raw)
    assert parsed is not None, "failed to salvage: " + repr(raw)
    assert isinstance(parsed, dict)
    assert "a" in parsed


def test_parse_json_loose_rejects_garbage():
    assert parse_json_loose("not json at all") is None
    assert parse_json_loose("") is None
    assert parse_json_loose("[1,2,3]") is None, "a list is not a spec"


# --------------------------------------------------------------------------- #
# Merging
# --------------------------------------------------------------------------- #
def test_merge_deduplicates_by_name():
    p1 = PartialSpec(screens=[{"name": "App list", "purpose": "a"}])
    p2 = PartialSpec(screens=[{"name": "app list", "purpose": "b"}])
    merged = _merge_partials([p1, p2])
    assert len(merged.screens) == 1


def test_merge_unions_dependency_lists():
    p1 = PartialSpec(platform_dependencies=["camera"], caveats=["obfuscated"])
    p2 = PartialSpec(platform_dependencies=["camera", "gps"], caveats=["obfuscated"])
    merged = _merge_partials([p1, p2])
    assert merged.platform_dependencies == ["camera", "gps"]
    assert merged.caveats == ["obfuscated"]


def test_merge_keeps_distinct_screens():
    p1 = PartialSpec(screens=[{"name": "List"}])
    p2 = PartialSpec(screens=[{"name": "Detail"}])
    assert len(_merge_partials([p1, p2]).screens) == 2


# --------------------------------------------------------------------------- #
# Package resolution -- the bug that silently reduces everything to nothing
# --------------------------------------------------------------------------- #
def _report(
    pkg: str, main: str | None, components: list[str] | None = None
) -> RiskReport:
    return RiskReport(
        identity=AppIdentity(package=pkg, main_activity=main),
        components=[Component(kind="activity", name=n) for n in (components or [])],
    )


def test_resolve_prefix_handles_manifest_package_with_extra_segment(tmp_path: Path):
    """F-Droid's real shape: package org.fdroid.fdroid, code under org/fdroid."""
    for i in range(30):
        (tmp_path / "org" / "fdroid").mkdir(parents=True, exist_ok=True)
        (tmp_path / "org" / "fdroid" / f"C{i}.java").write_text(f"class C{i} {{}}")
    for i in range(50):
        (tmp_path / "org" / "jetbrains").mkdir(parents=True, exist_ok=True)
        (tmp_path / "org" / "jetbrains" / f"J{i}.java").write_text(f"class J{i} {{}}")

    report = _report(
        "org.fdroid.fdroid",
        "org.fdroid.IconActivity",
        ["org.fdroid.MainActivity", "org.acra.sender.JobSenderService"],
    )
    resolved = resolve_app_prefixes(report, tmp_path, min_classes=20)
    assert resolved == ["org/fdroid"], "must not widen to org/ or match org.fdroid.fdroid"


def test_resolve_prefers_narrowest_covering_prefix(tmp_path: Path):
    for i in range(30):
        (tmp_path / "com" / "acme" / "app").mkdir(parents=True, exist_ok=True)
        (tmp_path / "com" / "acme" / "app" / f"A{i}.java").write_text(f"class A{i} {{}}")
    report = _report("com.acme.app", "com.acme.app.MainActivity")
    assert resolve_app_prefixes(report, tmp_path, min_classes=10) == ["com/acme/app"]


def test_resolve_falls_back_when_source_layout_is_unknown(tmp_path: Path):
    (tmp_path / "unrelated").mkdir(parents=True, exist_ok=True)
    (tmp_path / "unrelated" / "A.java").write_text("class A {}")
    report = _report("com.acme.app", "com.acme.app.MainActivity")
    resolved = resolve_app_prefixes(report, tmp_path, min_classes=20)
    assert resolved == ["com/acme/app"], "fall back to the manifest package"


def test_resolve_handles_empty_tree(tmp_path: Path):
    report = _report("com.acme.app", "com.acme.app.MainActivity")
    assert resolve_app_prefixes(report, tmp_path) == ["com/acme/app"]


# --------------------------------------------------------------------------- #
# Prompt facts
# --------------------------------------------------------------------------- #
def test_static_facts_include_ground_truth():
    report = RiskReport(
        identity=AppIdentity(package="com.acme.app", app_name="Acme"),
        endpoints=[
            {
                "value": "https://api.acme.test/v1",
                "scheme": "https",
                "source": "code",
                "confidence": "high",
            }
        ],
        sdks=[{"name": "OkHttp", "category": "networking"}],
        components=[Component(kind="activity", name="com.acme.app.Home")],
    )
    facts = render_static_facts(report)
    assert "com.acme.app" in facts
    assert "api.acme.test" in facts
    assert "OkHttp" in facts
    assert "Home" in facts


# --------------------------------------------------------------------------- #
# Spec contract
# --------------------------------------------------------------------------- #
def test_behaviour_spec_tolerates_minimal_payload():
    spec = BehaviourSpec.model_validate({"package": "com.acme.app"})
    assert spec.screens == []
    assert spec.purpose == ""


def test_behaviour_spec_renders_markdown():
    spec = BehaviourSpec(
        app_name="Acme",
        package="com.acme.app",
        purpose="Tracks expenses.",
        screens=[{"name": "List", "purpose": "see expenses", "shows": ["rows"]}],
        caveats=["static analysis only"],
    )
    md = spec.to_markdown()
    assert "Acme" in md
    assert "Tracks expenses." in md
    assert "List" in md
    assert "static analysis only" in md
