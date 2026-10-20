"""
Structural analysis: components, exported surface, native code, obfuscation.

The most useful single signal here is **exported components without a
permission guard**. An exported component is reachable by any app on the
device. If it is also unguarded, that is a concrete attack surface a security
engineer would flag immediately.
"""

from __future__ import annotations

from ..models import Category, Confidence, Finding, NativeLib, Severity


def analyse_export_surface(components: list) -> list[Finding]:
    """Flag exported components that lack a permission guard.

    Important carve-out: a launcher activity is *expected* to be exported with
    no permission. The launcher has to be reachable by the system. Flagging it
    is pure noise, and a tool that reports every well-behaved app as risky
    stops being read. So launcher activities are recorded at INFO, and
    everything else gets graded by kind.
    """
    findings: list[Finding] = []
    unguarded = [c for c in components if c.exported and not c.permission]

    for comp in unguarded:
        is_launcher = comp.kind == "activity" and "LAUNCHER" in comp.intent_filters

        if is_launcher:
            severity = Severity.INFO
            why = (
                "Launcher activity. Exported without a permission, which is "
                "expected and required for the home screen to start the app."
            )
        elif comp.kind == "provider":
            severity = Severity.HIGH
            why = (
                "Exported content provider with no permission. Any app on the "
                "device can read from it."
            )
        elif comp.kind == "receiver":
            severity = Severity.MEDIUM
            why = (
                "Exported broadcast receiver with no permission. Any app can "
                "send it an intent."
            )
        else:
            severity = Severity.MEDIUM
            why = "Exported component with no permission guard."

        findings.append(
            Finding(
                category=Category.COMPONENT,
                title=f"Exported {comp.kind}: {comp.name}",
                detail=why,
                severity=severity,
                confidence=Confidence.HIGH,
                location="AndroidManifest.xml",
                evidence=comp.intent_filters[:5],
                metadata={
                    "component": comp.name,
                    "kind": comp.kind,
                    "is_launcher": is_launcher,
                    "intent_filters": comp.intent_filters,
                },
            )
        )

    return findings


def analyse_native_libs(native_libs: dict) -> tuple[list[NativeLib], list[Finding]]:
    """Describe native code shipped with the app."""
    out: list[NativeLib] = []
    findings: list[Finding] = []

    for name, meta in sorted(native_libs.items()):
        out.append(
            NativeLib(
                name=name,
                abis=sorted(meta.get("abis", [])),
                size_bytes=int(meta.get("size_bytes", 0)),
            )
        )

    if out:
        total = sum(n.size_bytes for n in out)
        findings.append(
            Finding(
                category=Category.NATIVE,
                title=f"{len(out)} native librar{'y' if len(out) == 1 else 'ies'} bundled",
                detail=(
                    "Native code cannot be decompiled back to source. Later "
                    "stages will treat these libraries as a black box."
                ),
                severity=Severity.INFO,
                confidence=Confidence.HIGH,
                evidence=[n.name for n in out],
                metadata={
                    "total_size_bytes": total,
                    "abis": sorted({a for n in out for a in n.abis}),
                },
            )
        )

    return out, findings


def obfuscation_metrics(loaded, package: str) -> dict[str, float]:
    """Estimate how heavily an app is obfuscated.

    Obfuscated apps have short, meaningless class names. A high ratio of
    single- or double-character class names means the behaviour-reconstruction
    stage will get much less signal from the original code, and that fact
    belongs in the report rather than being discovered three stages later.
    """
    classes = loaded.dex.classes
    if not classes:
        return {"short_name_ratio": 0.0, "avg_class_name_length": 0.0}

    def readable(c: str) -> str:
        return c.strip("L;").replace("/", ".").split("$")[0]

    names = [readable(c) for c in classes]
    simple = [n.rsplit(".", 1)[-1] for n in names]

    short = sum(1 for s in simple if len(s) <= 2)
    return {
        "short_name_ratio": round(short / len(simple), 4),
        "avg_class_name_length": round(sum(len(s) for s in simple) / len(simple), 2),
        "total_classes": len(classes),
    }


#: Namespaces owned by libraries, never by the app being analysed.
_LIBRARY_NAMESPACES = (
    "androidx.",
    "android.",
    "com.google.",
    "com.android.",
    "kotlin.",
    "kotlinx.",
    "com.squareup.",
    "dagger.",
    "javax.",
    "java.",
    "sun.",
    "org.jetbrains.",
    "org.json.",
    "org.apache.",
)


def resolve_own_class_prefix(
    classes: list[str],
    package: str,
    entry_point: str | None,
    min_classes: int = 20,
) -> str:
    """Return the DEX prefix holding the app's own classes, e.g. ``Lorg/fdroid``.

    The manifest package is not a reliable prefix. F-Droid declares
    ``org.fdroid.fdroid`` but most of its code lives under ``org.fdroid``;
    filtering on the declared package counted 161 own classes when the app
    actually ships 3,881, which made it look almost entirely third-party.

    The rule is the narrowest prefix that still covers the launcher activity and
    matches a meaningful number of classes. Trimming stops as soon as the entry
    point falls outside the prefix, which is what stops the walk at
    ``org/fdroid`` instead of sliding up to ``org`` and collecting bouncycastle.

    This mirrors ``understand.pipeline.resolve_app_prefixes``, which solves the
    same problem against decompiled files. It is a separate implementation
    because these metrics come from DEX class names, before anything is
    decompiled.
    """
    if not classes:
        return ""

    def count(prefix: str) -> int:
        needle = "L" + prefix + "/"
        return sum(1 for c in classes if c.startswith(needle))

    def covers(prefix: str, fqcn: str | None) -> bool:
        if not fqcn:
            return False
        dotted = prefix.replace("/", ".")
        return fqcn == dotted or fqcn.startswith(dotted + ".")

    def owned(dotted: str) -> bool:
        return not dotted.startswith(_LIBRARY_NAMESPACES)

    # Narrowest first: each package is trimmed from the right, so a more
    # specific prefix is always tried before its parent.
    candidates: list[str] = []

    def add(dotted: str) -> None:
        parts = [p for p in dotted.split(".") if p]
        for i in range(len(parts), 0, -1):
            candidate = "/".join(parts[:i])
            if candidate not in candidates and owned(candidate.replace("/", ".") + "."):
                candidates.append(candidate)

    add(package)
    if entry_point and "." in entry_point:
        add(entry_point.rsplit(".", 1)[0])

    for candidate in candidates:
        if covers(candidate, entry_point) and count(candidate) >= min_classes:
            return "L" + candidate

    # Nothing covers the entry point. The declared package is still the safest
    # narrow guess when it captured anything at all.
    declared = package.replace(".", "/")
    if declared and count(declared) > 0:
        return "L" + declared

    for candidate in candidates:
        if count(candidate) >= min_classes:
            return "L" + candidate

    return "L" + candidates[0] if candidates else ""


def collect_metrics(loaded, components: list, endpoints: list) -> dict:
    """Assemble the numeric summary attached to a RiskReport."""
    ident_package = loaded.apk.get_package() or ""

    # The launcher activity names a real class, so its package is app code by
    # construction. It is a better anchor than the manifest package, which can
    # carry a flavour or version segment that never appears in the source tree.
    entry_point = next(
        (
            c.name
            for c in components
            if c.kind == "activity" and "LAUNCHER" in c.intent_filters
        ),
        None,
    )
    own_prefix = resolve_own_class_prefix(loaded.dex.classes, ident_package, entry_point)

    own_classes = [c for c in loaded.dex.classes if c.startswith(own_prefix + "/")]

    third_party = len(loaded.dex.classes) - len(own_classes)

    return {
        "dex_count": loaded.dex.dex_count,
        "total_classes": len(loaded.dex.classes),
        "own_classes": len(own_classes),
        "third_party_classes": third_party,
        "third_party_ratio": round(third_party / max(len(loaded.dex.classes), 1), 4),
        "total_methods": len(loaded.dex.methods),
        "total_strings": len(loaded.dex.strings),
        "printable_strings": len(loaded.dex.printable_strings),
        "component_count": len(components),
        "exported_components": sum(1 for c in components if c.exported),
        "endpoint_count": len(endpoints),
        "native_lib_count": len(loaded.native_libs),
        **obfuscation_metrics(loaded, ident_package),
    }
