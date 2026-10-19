"""
The orchestration layer -- one function that runs the whole M1 pipeline.

Keeping this in a single place matters for two reasons:

1. The later LLM stages slot in here without touching the analysers.
2. It gives us one honest place to record *what was not done*. An analysis
   tool that silently omits a check is worse than one that says so.
"""

from __future__ import annotations

from pathlib import Path

from .analyze import (
    analyse_crypto,
    analyse_endpoints,
    analyse_export_surface,
    analyse_native_libs,
    analyse_permissions,
    analyse_sdks,
    analyse_webview,
    collect_metrics,
)
from .ingest import load_apk, parse_components, parse_identity, parse_manifest_deeplinks
from .models import RiskReport


def analyse(
    apk_path: str | Path,
    *,
    progress: bool = False,
) -> RiskReport:
    """Run full static analysis on an APK and return a RiskReport.

    Parameters
    ----------
    apk_path
        Path to the APK.
    progress
        Print a short line per stage. Useful when running on a big APK where
        the whole run takes a few seconds and silence looks like a hang.

    Returns
    -------
    RiskReport

    Raises
    ------
    ApkSmithError
        If the APK cannot be read. Errors are deliberately not swallowed:
        a report that silently describes nothing is a failure mode that hides
        real bugs.
    """
    def say(msg: str) -> None:
        if progress:
            print(f"  [apksmith] {msg}")

    say("ingesting")
    loaded = load_apk(apk_path)

    say("parsing manifest")
    identity = parse_identity(loaded)
    components = parse_components(loaded)
    manifest_links = parse_manifest_deeplinks(loaded)

    say("checking permissions")
    permissions, f_perms = analyse_permissions(loaded)

    say("extracting endpoints")
    endpoints, f_endpoints = analyse_endpoints(loaded)

    say("inspecting WebView bridges")
    bridges, f_webview = analyse_webview(loaded)

    say("detecting crypto")
    crypto, f_crypto = analyse_crypto(loaded)

    say("fingerprinting SDKs")
    sdks = analyse_sdks(loaded)

    say("mapping component surface")
    native_libs, f_native = analyse_native_libs(loaded.native_libs)

    findings: list = []
    findings.extend(f_perms)
    findings.extend(f_endpoints)
    findings.extend(f_webview)
    findings.extend(f_crypto)
    findings.extend(f_native)
    findings.extend(analyse_export_surface(components))

    # Most severe first, so a truncated report still leads with what matters.
    findings.sort(key=lambda f: (-f.severity.weight, f.category.value))

    say("collecting metrics")
    metrics = collect_metrics(loaded, components, endpoints)

    return RiskReport(
        identity=identity,
        permissions=permissions,
        components=components,
        endpoints=endpoints,
        deeplinks=manifest_links,
        webview_bridges=bridges,
        crypto=crypto,
        sdks=sdks,
        native_libs=native_libs,
        findings=findings,
        metrics=metrics,
        apk_sha256=loaded.sha256,
        apk_size_bytes=loaded.size_bytes,
    )


def coverage_notes() -> list[str]:
    """What M1 does *not* do. Printed by the CLI so nobody over-trusts it."""
    return [
        "String-pool matching is not dataflow analysis. A present string is "
        "not proof a code path reaches it.",
        "No dynamic analysis. Runtime behaviour, Frida hooks and traffic are "
        "out of scope for M1.",
        "Native (.so) libraries are inventoried but not analysed.",
        "Packed or obfuscated APKs will under-report. Check the "
        "short_name_ratio metric to see how much signal you are getting.",
        "Manifest findings are high confidence; code-derived findings are "
        "medium at best and carry their evidence for manual verification.",
    ]