"""
Tests for APKSmith M1.

Two tiers:

1. **Unit tests** run with no fixture APK. They cover the pure logic --
   severity weighting, URL filtering, key heuristics, risk scoring. These are
   fast and must never break.

2. **Integration tests** run against a real APK in ``samples/``. They are
   skipped when it is absent, so a fresh clone still has a green suite. Fetch
   it with ``scripts/fetch_samples.sh``.
"""

from __future__ import annotations

import math
from pathlib import Path

import pytest

from apksmith.analyze.code import _looks_like_key, analyse_endpoints
from apksmith.analyze.structure import analyse_export_surface, obfuscation_metrics
from apksmith.models import Category, Confidence, Finding, Severity
from apksmith.report import to_json, to_markdown, to_terminal

SAMPLE_APK = Path(__file__).resolve().parents[1] / "samples" / "F-Droid.apk"
needs_apk = pytest.mark.skipif(
    not SAMPLE_APK.exists(),
    reason="sample APK not fetched; run scripts/fetch_samples.sh",
)


# --------------------------------------------------------------------------- #
# Unit tests: no fixture required
# --------------------------------------------------------------------------- #
def test_severity_weights_are_ordered():
    assert (
        Severity.INFO.weight
        < Severity.LOW.weight
        < Severity.MEDIUM.weight
        < Severity.HIGH.weight
        < Severity.CRITICAL.weight
    )


def test_risk_score_is_zero_when_no_findings():
    from apksmith.models import AppIdentity, RiskReport

    report = RiskReport(identity=AppIdentity(package="com.example"))
    assert report.risk_score == 0


def test_risk_score_saturates_without_pinning_at_100():
    """Many medium findings must not read the same as a critical one."""
    from apksmith.models import AppIdentity, RiskReport

    def build(n: int) -> RiskReport:
        return RiskReport(
            identity=AppIdentity(package="com.example"),
            findings=[
                Finding(category=Category.METADATA, title="x", severity=Severity.MEDIUM)
                for _ in range(n)
            ],
        )

    low = build(2).risk_score
    mid = build(8).risk_score
    high = build(30).risk_score

    assert low < mid < high <= 100
    # A single medium finding should not already look alarming.
    assert low < 25


def test_risk_score_matches_documented_curve():
    from apksmith.models import AppIdentity, RiskReport

    report = RiskReport(
        identity=AppIdentity(package="com.example"),
        findings=[
            Finding(category=Category.METADATA, title="x", severity=Severity.LOW)
            for _ in range(20)  # 20 * 5 = 100 total
        ],
    )
    expected = round(100 * (1 - math.exp(-100 / 200)))
    assert report.risk_score == expected


@pytest.mark.parametrize(
    "value,expected",
    [
        ("0" * 56, False),  # sentinel padding
        ("f" * 64, False),  # sentinel
        ("00000000000000000000000000000000ab", False),  # mostly zeros + tail
        ("4a7f2b9e1c8d0a3f6b5e2d7c9a1f4e8b", True),  # real-looking key
        ("too-short", False),
        ("ZZZZ0000000000000000000000000000", False),  # not hex
    ],
)
def test_key_heuristic_rejects_placeholders(value, expected):
    assert _looks_like_key(value) is expected


class _FakeDex:
    def __init__(self, strings):
        self.strings = strings
        self.classes: list[str] = []

    @property
    def printable_strings(self):
        return self.strings


class _FakeLoaded:
    def __init__(self, strings):
        self.dex = _FakeDex(strings)


def test_endpoint_extraction_filters_noise_hosts():
    loaded = _FakeLoaded(
        [
            "https://api.production.example/v1/users",
            "http://schemas.android.com/apk/res/android",
            "https://schemas.android.com/activity",
            "http://example.com/placeholder",
            "not-a-url-at-all",
        ]
    )
    endpoints, _ = analyse_endpoints(loaded)
    hosts = {e.host for e in endpoints}
    assert hosts == {"api.production.example"}


def test_plaintext_http_is_flagged():
    loaded = _FakeLoaded(["http://api.thing.example/v1"])
    _, findings = analyse_endpoints(loaded)
    assert any("plain HTTP" in f.title for f in findings)


def test_launcher_activity_is_not_a_risk():
    from apksmith.models import Component

    launcher = Component(
        kind="activity",
        name="com.example.MainActivity",
        exported=True,
        permission=None,
        intent_filters=["MAIN", "LAUNCHER"],
    )
    findings = analyse_export_surface([launcher])
    assert len(findings) == 1
    assert findings[0].severity == Severity.INFO


def test_unguarded_provider_is_high():
    from apksmith.models import Component

    provider = Component(
        kind="provider", name="com.example.DataProvider", exported=True, permission=None
    )
    findings = analyse_export_surface([provider])
    assert findings[0].severity == Severity.HIGH


def test_guarded_component_is_not_flagged():
    from apksmith.models import Component

    guarded = Component(
        kind="receiver",
        name="com.example.R",
        exported=True,
        permission="android.permission.BIND_JOB_SERVICE",
    )
    assert analyse_export_surface([guarded]) == []


def test_obfuscation_metrics_on_synthetic_names():
    class D:
        classes = ["La;", "Lb;", "Lc;", "Lcom/example/Foo;", "Lcom/example/Bar;"]

    class L:
        dex = D()
        apk = type("A", (), {"get_package": staticmethod(lambda: "com.example")})()

    m = obfuscation_metrics(L(), "com.example")
    assert m["total_classes"] == 5
    assert 0.0 <= m["short_name_ratio"] <= 1.0


def test_renderers_do_not_crash_on_minimal_report():
    from apksmith.models import AppIdentity, RiskReport

    report = RiskReport(identity=AppIdentity(package="com.example"))
    assert "com.example" in to_terminal(report)
    assert "com.example" in to_markdown(report)
    assert "com.example" in to_json(report)


# --------------------------------------------------------------------------- #
# Integration tests: need the sample APK
# --------------------------------------------------------------------------- #
@needs_apk
def test_analyse_real_apk_produces_sane_report():
    from apksmith.app import analyse

    report = analyse(SAMPLE_APK)

    # Identity we know to be true of F-Droid.
    assert report.identity.package == "org.fdroid.fdroid"
    assert report.identity.min_sdk is not None

    # Non-zero work actually happened.
    assert report.metrics["total_classes"] > 1000
    assert len(report.components) > 10
    assert report.apk_sha256 and len(report.apk_sha256) == 64

    # A well-behaved open-source app must not score near maximum.
    assert report.risk_score < 95, (
        f"risk score {report.risk_score} suggests a false positive storm"
    )


@needs_apk
def test_every_finding_has_evidence_or_is_informational():
    """High-confidence, high-severity claims must be backed by something."""
    from apksmith.app import analyse

    report = analyse(SAMPLE_APK)
    for f in report.findings:
        if f.severity.weight >= 30 and f.confidence == Confidence.HIGH:
            assert f.evidence or f.location, f"unsupported high-severity claim: {f.title}"


@needs_apk
def test_manifest_and_deeplink_parsing():
    from apksmith.ingest import load_apk, parse_manifest_deeplinks

    loaded = load_apk(SAMPLE_APK)
    links = parse_manifest_deeplinks(loaded)
    assert links, "expected at least one manifest deep link"
    assert all(link.scheme for link in links)
