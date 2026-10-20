"""
Code-derived analysis: endpoints, WebView bridges and cryptography.

Everything here works off the DEX string pool and the method table. That is
fast and dependency-free, but it has an honest limitation: **a string in the
pool is not proof a code path reaches it.** A value may sit in a constant pool
and never execute.

We therefore tag every result with a confidence level and keep the literal
evidence, so a human or a later LLM stage can verify rather than trust. The
expensive alternative -- real cross-reference analysis through the CFG -- is
planned for the next milestone.
"""

from __future__ import annotations

import re
from urllib.parse import urlparse

from ..models import (
    Category,
    Confidence,
    CryptoUse,
    Endpoint,
    Finding,
    Severity,
    WebViewBridge,
)

# --------------------------------------------------------------------------- #
# Endpoints
# --------------------------------------------------------------------------- #
_URL_RE = re.compile(
    r"^(https?|wss?|ftp)://"
    r"[A-Za-z0-9._~%:@!$&'()*+,;=-]+"
    r"(?::\d{1,5})?"
    r"(?:/[^\s]*)?$",
    re.IGNORECASE,
)

#: Hosts that are never a real third-party service. Skipped so the report is
#: about what an app talks to, not about test fixtures inside the SDK.
_NOISE_HOSTS = {
    "schemas.android.com",
    "www.w3.org",
    "www.apache.org",
    "ns.adobe.com",
    "xmlpull.org",
    "localhost",
    "127.0.0.1",
    "example.com",
    "example.org",
    "example.net",
}

#: Path fragments that indicate the endpoint is not a network API.
_NOISE_PATH_HINTS = ("schemas.android.com", "/xml/", "schemas.microsoft.com")


def analyse_endpoints(loaded) -> tuple[list[Endpoint], list[Finding]]:
    """Extract network endpoints from the DEX string pool."""
    out: dict[str, Endpoint] = {}
    findings: list[Finding] = []

    for raw in loaded.dex.printable_strings:
        candidate = raw.strip()
        if len(candidate) < 8 or len(candidate) > 2000:
            continue
        if not _URL_RE.match(candidate):
            continue

        try:
            parts = urlparse(candidate)
        except Exception:
            continue

        host = (parts.hostname or "").lower()
        if not host or host in _NOISE_HOSTS:
            continue
        if any(hint in candidate for hint in _NOISE_PATH_HINTS):
            continue

        scheme = (parts.scheme or "").lower()
        # Plain HTTP means traffic is visible to any network observer.
        confidence = Confidence.HIGH if scheme == "https" else Confidence.MEDIUM

        if candidate not in out:
            out[candidate] = Endpoint(
                value=candidate,
                scheme=scheme,
                host=host,
                path=parts.path or None,
                source="code",
                confidence=confidence,
            )

    endpoints = sorted(out.values(), key=lambda e: e.host or "")

    plaintext = [e for e in endpoints if e.scheme == "http"]
    if plaintext:
        findings.append(
            Finding(
                category=Category.ENDPOINT,
                title=f"{len(plaintext)} endpoint(s) use plain HTTP",
                detail="Traffic over http:// is readable by anyone on the network path.",
                severity=Severity.MEDIUM,
                confidence=Confidence.HIGH,
                evidence=[e.value for e in plaintext[:10]],
                metadata={"count": len(plaintext)},
            )
        )

    return endpoints, findings


# --------------------------------------------------------------------------- #
# WebView JavaScript bridges
# --------------------------------------------------------------------------- #
# addJavascriptInterface is the dangerous call: it publishes Java objects to
# web content. If the WebView loads any URL the app does not control, that
# page can call the exposed methods.
_ADD_JS_INTERFACE = "addJavascriptInterface"
_LOAD_URL_METHODS = ("loadUrl", "loadDataWithBaseURL", "loadData")
_WEBVIEW_CLASS = "android.webkit.WebView"
_SET_JAVASCRIPT_ENABLED = "setJavaScriptEnabled"


def analyse_webview(loaded) -> tuple[list[WebViewBridge], list[Finding]]:
    """Find JavaScript interfaces exposed to web content.

    We cannot recover the exact object graph from strings alone, so we infer:
    if an app calls ``addJavascriptInterface`` we report the WebView as a
    bridge surface and report whether JavaScript is enabled and whether
    arbitrary URLs are loaded. That combination is the thing to look at.
    """
    methods = {m for _, m in loaded.dex.methods}
    printable = loaded.dex.printable_strings

    uses_add_interface = _ADD_JS_INTERFACE in printable
    uses_webview = any("Landroid/webkit/WebView" in c for c in loaded.dex.classes)
    js_enabled = _SET_JAVASCRIPT_ENABLED in printable
    loads_urls = any(m in methods for m in _LOAD_URL_METHODS)

    if not uses_webview or not uses_add_interface:
        return [], []

    severity = Severity.MEDIUM
    detail = "App exposes Java objects to a WebView via addJavascriptInterface."
    if js_enabled and loads_urls:
        severity = Severity.HIGH
        detail += (
            " JavaScript is enabled and the app loads URLs, so any page it "
            "loads can call those exposed methods."
        )

    bridges = [
        WebViewBridge(
            interface_name="(inferred WebView bridge)",
            methods=sorted(
                m
                for m in methods
                if m.startswith(("exec", "invoke", "call", "run", "get", "set", "on"))
                and len(m) < 40
            )[:40],
            accepts_origin=None,
            severity=severity,
            detail=detail,
        )
    ]

    findings = [
        Finding(
            category=Category.WEBVIEW,
            title="JavaScript bridge exposed to WebView",
            detail=detail,
            severity=severity,
            # Medium confidence on purpose: string presence is not a dataflow
            # proof. This is exactly the kind of thing to confirm by hand.
            confidence=Confidence.MEDIUM,
            evidence=[
                _ADD_JS_INTERFACE,
                _SET_JAVASCRIPT_ENABLED if js_enabled else None,
                _WEBVIEW_CLASS,
            ],
            metadata={
                "javascript_enabled": js_enabled,
                "loads_urls": loads_urls,
            },
        )
    ]

    return bridges, findings


# --------------------------------------------------------------------------- #
# Cryptography
# --------------------------------------------------------------------------- #
_CRYPTO_PRIMITIVES: list[tuple[str, Severity, str]] = [
    ("javax.crypto.spec.DES", Severity.MEDIUM, "DES is broken. Should not be used."),
    ("DES/ECB", Severity.HIGH, "DES with ECB mode leaks plaintext structure."),
    ("DES/CBC", Severity.MEDIUM, "DES is broken regardless of mode."),
    ("RC4", Severity.HIGH, "RC4 is cryptographically broken."),
    ("MD5", Severity.MEDIUM, "MD5 is broken for collision resistance."),
    ("SHA1", Severity.LOW, "SHA-1 is deprecated for signatures."),
    ("ECB", Severity.HIGH, "ECB mode does not hide patterns in plaintext."),
    ("Cipher.getInstance", Severity.LOW, "Uses the platform crypto provider."),
    ("javax.crypto.SecretKeySpec", Severity.LOW, "Symmetric key handling."),
    ("java.security.MessageDigest", Severity.LOW, "Hashing in use."),
]

#: Hardcoded-key heuristic: a 16/24/32 char hex-looking string near a cipher
#: marker is a strong hint. Reported as LOW confidence only.
_AES_KEY_RE = re.compile(r"^[0-9a-fA-F]{32,64}$")


def _looks_like_key(value: str) -> bool:
    """Reject the obvious non-keys before reporting a hardcoded key.

    A plain length-and-hexmatch check produced a false positive on F-Droid's
    all-zero placeholder string. Padding and sentinel values are everywhere in
    real string pools, so we require some variety in the hex digits before we
    call something a key.
    """
    if not _AES_KEY_RE.match(value):
        return False
    # A real key does not consist of one digit repeated, nor of a long run of
    # a single digit followed by a short tail. Require genuine variety.
    return len({c.lower() for c in value}) >= 6


def analyse_crypto(loaded) -> tuple[list[CryptoUse], list[Finding]]:
    """Detect cryptographic primitives, and flag deprecated ones."""
    printable = loaded.dex.printable_strings
    blob = "\n".join(printable)

    found: list[CryptoUse] = []
    findings: list[Finding] = []

    for marker, severity, why in _CRYPTO_PRIMITIVES:
        if marker not in blob:
            continue
        found.append(CryptoUse(primitive=marker, detail=why, severity=severity))
        if severity.weight >= 15:
            findings.append(
                Finding(
                    category=Category.CRYPTO,
                    title=f"Weak or misused crypto: {marker}",
                    # A modern app bundles dozens of libraries, and a weak
                    # primitive is very often inside one of them rather than in
                    # the app's own code. Say so, and keep confidence honest.
                    detail=(
                        f"{why} Note this may come from a bundled dependency "
                        "rather than the app's own code -- string-pool presence "
                        "does not identify the owning class."
                    ),
                    severity=severity,
                    confidence=Confidence.LOW,
                    evidence=[marker],
                )
            )

    # Possible hardcoded symmetric key.
    if "javax.crypto" in blob:
        candidates = [s for s in printable if _looks_like_key(s)]
        if candidates:
            findings.append(
                Finding(
                    category=Category.CRYPTO,
                    title="Possible hardcoded encryption key",
                    detail=(
                        "A hex string of key length appears in the string pool "
                        "alongside crypto APIs. Confirm before treating as real."
                    ),
                    severity=Severity.HIGH,
                    confidence=Confidence.LOW,
                    evidence=candidates[:3],
                )
            )

    return found, findings
