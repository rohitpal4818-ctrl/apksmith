"""APKSmith -- static analysis and behaviour extraction from Android APKs.

The pipeline is deliberately staged so each stage can be tested and explained
on its own:

    ingest   APK file  ->  parsed objects (manifest tree, DEX, native libs)
    analyze  parsed    ->  typed findings (permissions, endpoints, bridges, ...)
    report   findings  ->  JSON / Markdown / terminal output

Later stages add an LLM understanding layer that turns findings plus decompiled
source into a behaviour spec, and a generation layer that turns that spec into
new source code.

Quick start
-----------
    from apksmith import analyse
    report = analyse("app.apk")
    print(report.identity.app_name)
"""

from __future__ import annotations

__version__ = "0.2.0"

from .models import (  # noqa: F401
    AppIdentity,
    Category,
    Component,
    Confidence,
    CryptoUse,
    Endpoint,
    Finding,
    NativeLib,
    PermissionUse,
    RiskReport,
    Severity,
    ThirdPartySDK,
    WebViewBridge,
)

__all__ = [
    "__version__",
    "AppIdentity",
    "Category",
    "Component",
    "Confidence",
    "CryptoUse",
    "Endpoint",
    "Finding",
    "NativeLib",
    "PermissionUse",
    "RiskReport",
    "Severity",
    "ThirdPartySDK",
    "WebViewBridge",
]