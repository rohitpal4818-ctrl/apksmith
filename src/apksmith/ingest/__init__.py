"""Ingest stage: APK file -> parsed objects.

Public surface:

    load_apk(path)                     -> LoadedApk
    parse_identity(loaded)             -> AppIdentity
    parse_components(loaded)           -> list[Component]
    parse_manifest_deeplinks(loaded)   -> list[Endpoint]

jadx decompilation is optional and lives behind :mod:`apksmith.ingest.jadx`.
"""

from __future__ import annotations

from .apkfile import DexBundle, LoadedApk, load_apk, sha256_of
from .manifest import (
    parse_components,
    parse_identity,
    parse_manifest_deeplinks,
)

__all__ = [
    "DexBundle",
    "LoadedApk",
    "load_apk",
    "sha256_of",
    "parse_identity",
    "parse_components",
    "parse_manifest_deeplinks",
]
