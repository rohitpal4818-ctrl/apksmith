"""
Report rendering: RiskReport -> terminal, Markdown, or JSON.

Three audiences:

- **Terminal** -- a human scanning results. Colour-coded severity, counts first.
- **Markdown** -- for a GitHub README or a pull request.
- **JSON** -- for the later LLM stages and for machine consumption.

Terminal output is written with plain ASCII by default. Windows consoles in
particular mangle box-drawing characters and emoji, and a report you cannot
read is a failed report.
"""

from __future__ import annotations

import json
from typing import Any

from ..models import RiskReport, Severity

_SEVERITY_LABEL = {
    Severity.CRITICAL: "CRITICAL",
    Severity.HIGH: "HIGH",
    Severity.MEDIUM: "MEDIUM",
    Severity.LOW: "LOW",
    Severity.INFO: "INFO",
}


def to_json(report: RiskReport, indent: int = 2) -> str:
    """Serialise the full report as JSON."""
    payload: dict[str, Any] = report.model_dump(mode="json")
    payload["risk_score"] = report.risk_score
    return json.dumps(payload, indent=indent, ensure_ascii=False)


def _fmt_bytes(n: int) -> str:
    step = 1024.0
    value = float(n)
    for unit in ("B", "KB", "MB", "GB"):
        if value < step:
            return f"{value:.0f}{unit}" if unit == "B" else f"{value:.1f}{unit}"
        value /= step
    return f"{value:.1f}TB"


def to_markdown(report: RiskReport, max_findings: int = 40) -> str:
    """Render the report as Markdown."""
    i = report.identity
    m = report.metrics
    out: list[str] = []
    a = out.append

    a(f"# APKSmith report: {i.app_name or i.package}")
    a("")
    a(
        f"**Package** `{i.package}` &nbsp;|&nbsp; **Version** {i.version_name or '?'} "
        f"({i.version_code}) &nbsp;|&nbsp; **Risk score** {report.risk_score}/100"
    )
    a("")
    a(f"- SDK: min {i.min_sdk}, target {i.target_sdk}")
    a(f"- Main activity: `{i.main_activity}`")
    a(f"- Size: {_fmt_bytes(report.apk_size_bytes)}")
    a(f"- SHA-256: `{report.apk_sha256}`")
    a("")

    a("## Summary")
    a("")
    a("| Metric | Value |")
    a("| --- | --- |")
    for key in (
        "total_classes",
        "own_classes",
        "third_party_classes",
        "third_party_ratio",
        "total_methods",
        "endpoint_count",
        "component_count",
        "exported_components",
        "native_lib_count",
        "short_name_ratio",
    ):
        if key in m:
            a(f"| {key.replace('_', ' ')} | {m[key]} |")
    a("")

    sev_counts: dict[str, int] = {}
    for f in report.findings:
        sev_counts[f.severity.value] = sev_counts.get(f.severity.value, 0) + 1
    a(
        "**Findings by severity:** "
        + " &nbsp;|&nbsp; ".join(
            f"{_SEVERITY_LABEL[k]} {v}"
            for k, v in sorted(sev_counts.items(), key=lambda kv: -Severity(kv[0]).weight)
        )
    )
    a("")

    a("## Findings")
    a("")
    if not report.findings:
        a("_No findings._")
    else:
        a("| Severity | Finding | Confidence |")
        a("| --- | --- | --- |")
        for f in report.findings[:max_findings]:
            title = f.title.replace("|", "\\|")
            a(f"| **{_SEVERITY_LABEL[f.severity]}** | {title} | {f.confidence.value} |")
        if len(report.findings) > max_findings:
            a("")
            a(
                f"_{len(report.findings) - max_findings} further findings in the JSON output._"
            )
    a("")

    if report.permissions:
        a("## Permissions")
        a("")
        a("| Permission | Severity | Used in code | Why it matters |")
        a("| --- | --- | --- | --- |")
        for p in report.permissions[:30]:
            used = (
                "yes"
                if p.referenced_in_code
                else ("no" if p.referenced_in_code is False else "n/a")
            )
            a(
                f"| `{p.name.split('.')[-1]}` | {_SEVERITY_LABEL[p.severity]} | {used} | {p.reason} |"
            )
        a("")

    if report.components:
        exported = [c for c in report.components if c.exported]
        a(f"## Exported components ({len(exported)} of {len(report.components)})")
        a("")
        a("| Kind | Class | Guarded |")
        a("| --- | --- | --- |")
        for c in exported[:25]:
            guard = f"`{c.permission}`" if c.permission else "**none**"
            a(f"| {c.kind} | `{c.name}` | {guard} |")
        a("")

    if report.endpoints:
        a(f"## Endpoints ({len(report.endpoints)})")
        a("")
        a("| URL | Scheme |")
        a("| --- | --- |")
        for e in report.endpoints[:30]:
            a(f"| `{e.value}` | {e.scheme} |")
        a("")

    if report.sdks:
        a("## Third-party SDKs")
        a("")
        a("| SDK | Category |")
        a("| --- | --- |")
        for s in report.sdks:
            a(f"| {s.name} | {s.category} |")
        a("")

    return "\n".join(out)


def to_terminal(report: RiskReport, top_n: int = 12) -> str:
    """Compact human summary for a terminal."""
    i = report.identity
    m = report.metrics
    rule = "-" * 62
    out: list[str] = []
    a = out.append

    a(rule)
    a(f" {i.app_name or i.package}")
    a(f" {i.package}  v{i.version_name}  (SDK {i.min_sdk}->{i.target_sdk})")
    a(f" {_fmt_bytes(report.apk_size_bytes)}   sha256 {report.apk_sha256[:16]}...")
    a(rule)
    a(f" RISK SCORE          {report.risk_score}/100")
    a(
        f" classes / methods   {m.get('total_classes', 0):,} / {m.get('total_methods', 0):,}"
    )
    a(f" own code share      {1 - m.get('third_party_ratio', 0):.0%}")
    a(f" endpoints           {len(report.endpoints)}")
    a(
        f" components          {len(report.components)} "
        f"({m.get('exported_components', 0)} exported)"
    )
    a(f" native libs         {len(report.native_libs)}")
    a(f" obfuscation         {m.get('short_name_ratio', 0):.0%} short class names")
    a(f" SDKs identified     {len(report.sdks)}")
    a(rule)

    sev_counts: dict[str, int] = {}
    for f in report.findings:
        sev_counts[f.severity.value] = sev_counts.get(f.severity.value, 0) + 1
    if sev_counts:
        a(
            " FINDINGS: "
            + "  ".join(
                f"{_SEVERITY_LABEL[Severity(k)].title()}={v}"
                for k, v in sorted(
                    sev_counts.items(), key=lambda kv: -Severity(kv[0]).weight
                )
            )
        )
    else:
        a(" FINDINGS: none")
    a(rule)

    shown = report.findings[:top_n]
    for f in shown:
        a(f" [{_SEVERITY_LABEL[f.severity]:8}] {f.title}")
        if f.detail:
            first = f.detail if len(f.detail) <= 56 else f.detail[:53] + "..."
            a(f"             {first}")
        if f.evidence:
            ev = f.evidence[0]
            a(f"             evidence: {ev[:56]}")

    if len(report.findings) > top_n:
        a(f" ... and {len(report.findings) - top_n} more")
    a(rule)
    return "\n".join(out)
