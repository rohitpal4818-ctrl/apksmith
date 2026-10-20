"""
Core data models for APKSmith.

Every analyser produces typed findings. Findings are Pydantic models so that
they validate on creation, serialise cleanly to JSON, and can be consumed by
later pipeline stages (the LLM understanding layer) without extra plumbing.

Design note
-----------
We deliberately separate "what the app *declares*" (manifest) from "what the
app *does*" (DEX). A permission in the manifest is a claim. A call to
`TelephonyManager.getDeviceId()` in the code is evidence. Later stages reason
about the difference, so the models keep them apart.
"""

from __future__ import annotations

from enum import Enum
from typing import Any

from pydantic import BaseModel, Field


# --------------------------------------------------------------------------- #
# Severity / confidence primitives
# --------------------------------------------------------------------------- #
class Severity(str, Enum):
    """How much a finding matters. Drives the risk score."""

    INFO = "info"
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"

    @property
    def weight(self) -> int:
        """Contribution to the raw risk total, before saturation.

        INFO is zero on purpose: recording something without adding it to the
        score is how the report stays readable for a benign app.
        """
        return {
            Severity.INFO: 0,
            Severity.LOW: 5,
            Severity.MEDIUM: 15,
            Severity.HIGH: 30,
            Severity.CRITICAL: 50,
        }[self]


class Confidence(str, Enum):
    """How sure we are. Strings pulled from DEX are noisier than manifest entries."""

    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"


class Category(str, Enum):
    """Which analyser produced a finding. Used to group report sections."""

    METADATA = "metadata"
    PERMISSION = "permission"
    COMPONENT = "component"
    ENDPOINT = "endpoint"
    DEEPLINK = "deeplink"
    WEBVIEW = "webview"
    CRYPTO = "crypto"
    SDK = "sdk"
    NATIVE = "native"
    OBFUSCATION = "obfuscation"


# --------------------------------------------------------------------------- #
# Base finding
# --------------------------------------------------------------------------- #
class Finding(BaseModel):
    """A single observation about an app.

    Every analyser emits these. `evidence` holds the literal strings that led
    to the finding so a human (or a later LLM stage) can verify it rather than
    trust it.
    """

    category: Category
    title: str
    detail: str = ""
    severity: Severity = Severity.INFO
    confidence: Confidence = Confidence.HIGH
    evidence: list[str] = Field(default_factory=list)
    # Source location inside the APK, e.g. "AndroidManifest.xml" or a class name
    location: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


# --------------------------------------------------------------------------- #
# Manifest-derived structures
# --------------------------------------------------------------------------- #
class AppIdentity(BaseModel):
    """Who this app is."""

    package: str
    app_name: str | None = None
    version_name: str | None = None
    version_code: int | None = None
    min_sdk: int | None = None
    target_sdk: int | None = None
    main_activity: str | None = None
    application_label: str | None = None


class PermissionUse(BaseModel):
    """A declared permission plus why it matters."""

    name: str
    severity: Severity
    reason: str
    #: Whether the app actually references related APIs in its DEX.
    #: ``None`` means we could not determine it.
    referenced_in_code: bool | None = None


class Component(BaseModel):
    """An activity, service, receiver or provider."""

    kind: str  # activity | service | receiver | provider
    name: str
    exported: bool | None = None
    permission: str | None = None
    intent_filters: list[str] = Field(default_factory=list)
    deeplink_schemes: list[str] = Field(default_factory=list)


# --------------------------------------------------------------------------- #
# Code-derived structures
# --------------------------------------------------------------------------- #
class Endpoint(BaseModel):
    """A network endpoint discovered in code or resources."""

    value: str
    scheme: str | None = None
    host: str | None = None
    path: str | None = None
    #: ``manifest``, ``code`` or ``resource``
    source: str
    confidence: Confidence


class WebViewBridge(BaseModel):
    """A JavaScript interface exposed to web content.

    These matter because they let a web page call native code. A bridge named
    ``AndroidBridge`` with an ``exec`` method reachable from any URL is a
    serious finding.
    """

    interface_name: str
    methods: list[str] = Field(default_factory=list)
    accepts_origin: str | None = None
    severity: Severity = Severity.MEDIUM
    detail: str = ""


class NativeLib(BaseModel):
    """A native (.so) library shipped in the APK."""

    name: str
    abis: list[str] = Field(default_factory=list)
    size_bytes: int
    is_stripped: bool | None = None


class ThirdPartySDK(BaseModel):
    """A recognised third-party SDK, fingerprinted from class/package names."""

    name: str
    category: str
    evidence: list[str] = Field(default_factory=list)


class CryptoUse(BaseModel):
    """Use of a cryptographic primitive."""

    primitive: str
    detail: str = ""
    severity: Severity = Severity.LOW


# --------------------------------------------------------------------------- #
# Aggregate report
# --------------------------------------------------------------------------- #
class RiskReport(BaseModel):
    """The full output of one analysis run."""

    identity: AppIdentity
    permissions: list[PermissionUse] = Field(default_factory=list)
    components: list[Component] = Field(default_factory=list)
    endpoints: list[Endpoint] = Field(default_factory=list)
    deeplinks: list[Endpoint] = Field(default_factory=list)
    webview_bridges: list[WebViewBridge] = Field(default_factory=list)
    crypto: list[CryptoUse] = Field(default_factory=list)
    sdks: list[ThirdPartySDK] = Field(default_factory=list)
    native_libs: list[NativeLib] = Field(default_factory=list)
    findings: list[Finding] = Field(default_factory=list)

    # Cheap metrics that later stages (and humans) care about.
    metrics: dict[str, Any] = Field(default_factory=dict)

    #: SHA-256 of the APK, so results can be cached and cited.
    apk_sha256: str = ""
    apk_size_bytes: int = 0

    @property
    def risk_score(self) -> int:
        """A 0-100 risk score from the severity-weighted findings.

        Naively summing severity weights saturates immediately: six
        medium-severity findings reach 90 and every app looks identical. A
        saturating exponential is used instead so the score keeps growing in
        a meaningful way as evidence accumulates, without ever pinning a
        well-behaved app at 100.

            score = 100 * (1 - e^(-total / 200))

        Reference points: total 100 -> 39, 200 -> 63, 400 -> 86, 800 -> 98.
        """
        import math

        total = sum(f.severity.weight for f in self.findings)
        if total <= 0:
            return 0
        return int(round(100 * (1 - math.exp(-total / 200))))
