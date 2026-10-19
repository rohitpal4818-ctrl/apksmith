"""
Ingest stage: turn an APK file on disk into parsed Python objects.

Responsibilities
----------------
1. Validate the file is really an APK (a ZIP with AndroidManifest.xml).
2. Hash it, so downstream results can be cached and cited.
3. Parse the binary AndroidManifest.xml into a tree.
4. Load DEX bytecode for string and class extraction.
5. Optionally shell out to jadx for readable Java source.

Nothing in here interprets the app. Interpretation happens in `analyze/`.
"""

from __future__ import annotations

import contextlib
import hashlib
import zipfile
from collections.abc import Iterator
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from androguard.core.apk import APK
from androguard.core.dex import DEX

from ..errors import ApkNotFound, DexUnavailable
from ..logging_setup import configure_logging

#: Entry points that must exist for a file to be a usable APK.
_REQUIRED_ENTRIES = ("AndroidManifest.xml",)


@dataclass
class DexBundle:
    """All DEX files in an APK, flattened into one convenient view.

    Multi-APK (split APKs) and apps with many DEX files are common, so we
    merge rather than returning a list the caller has to remember to loop.
    """

    strings: list[str] = field(default_factory=list)
    #: Fully-qualified class names, e.g. ``Lcom/example/Foo;``
    classes: list[str] = field(default_factory=list)
    #: ``(class_name, method_name)`` pairs
    methods: list[tuple[str, str]] = field(default_factory=list)
    dex_count: int = 0
    #: Populated lazily by `printable_strings`.
    _printable_cache: list[str] | None = field(default=None, repr=False, compare=False)

    def __post_init__(self) -> None:
        # Each DEX lists its own strings. De-duplicate once, up front, so every
        # later stage can assume uniqueness.
        self.strings = sorted(set(self.strings))
        self.classes = sorted(set(self.classes))
        self.methods = sorted(set(self.methods))

    def has_string_fragment(self, fragment: str) -> bool:
        """True if any printable DEX string contains `fragment` (case-insensitive)."""
        needle = fragment.lower()
        return any(needle in s.lower() for s in self.printable_strings)

    @property
    def printable_strings(self) -> list[str]:
        """Only strings a human could actually read.

        The DEX string pool holds MUTF-8 blobs: control characters, lone
        surrogates and binary fragments appear constantly. Analysers want
        real text -- URLs, class names, log messages, permission strings.
        Anything with a control character or an unencodable codepoint is
        dropped.

        Cached, because it is called once per analyser and the pool is large.
        """
        if self._printable_cache is None:
            out: list[str] = []
            for s in self.strings:
                if not s:
                    continue
                if any(ord(ch) < 0x20 or ord(ch) == 0x7F for ch in s):
                    continue
                # Reject anything the user's terminal could not render.
                try:
                    s.encode("utf-8")
                except UnicodeEncodeError:
                    continue
                out.append(s)
            self._printable_cache = out
        return self._printable_cache


@dataclass
class LoadedApk:
    """Everything the ingest stage produced, ready for analysis."""

    path: Path
    apk: APK
    sha256: str
    size_bytes: int
    dex: DexBundle
    #: Native libraries found in lib/, keyed by lib name
    native_libs: dict[str, dict[str, Any]] = field(default_factory=dict)
    #: Best-effort readable Java sources from jadx, if it ran
    decompiled_root: Path | None = None

    # -- convenience ------------------------------------------------------- #
    def iter_zip_entries(self) -> Iterator[str]:
        """Names of every entry in the APK ZIP."""
        with zipfile.ZipFile(self.path, "r") as zf:
            yield from zf.namelist()

    @property
    def manifest_xml(self) -> Any:
        """The parsed AndroidManifest.xml as an lxml element tree."""
        return self.apk.get_android_manifest_xml()


def sha256_of(path: Path, chunk: int = 1 << 20) -> str:
    """Stream a SHA-256 over a file. Avoids loading huge APKs into memory."""
    h = hashlib.sha256()
    with path.open("rb") as fh:
        while block := fh.read(chunk):
            h.update(block)
    return h.hexdigest()


def _load_dex(apk: APK) -> DexBundle:
    """Extract strings, classes and methods from every DEX in the APK.

    androguard has changed this API shape across major versions, so we probe
    rather than assume. If we cannot get *anything*, raise -- a silently empty
    bundle would make every downstream analyser report "no findings", which is
    the worst possible failure mode for a security tool.
    """
    bundle = DexBundle()

    try:
        raw_dexes = apk.get_all_dex()
    except Exception as exc:  # pragma: no cover - depends on androguard internals
        raise DexUnavailable(f"Could not read DEX from APK: {exc}") from exc

    if raw_dexes is None:
        raise DexUnavailable("APK contains no DEX bytecode.")

    dexes: list[Any] = []

    # androguard has returned several shapes across versions. In 4.1.x
    # `get_all_dex()` yields *raw DEX bytes*; older versions yielded parsed
    # DEX objects. Normalise to a list of DEX objects here so that no
    # downstream code has to care.
    if isinstance(raw_dexes, (list, tuple)) or hasattr(raw_dexes, "__next__"):
        items = list(raw_dexes)
    elif raw_dexes is None:
        items = []
    else:
        items = [raw_dexes]

    for item in items:
        if isinstance(item, (bytes, bytearray)):
            try:
                d = DEX(bytes(item))
            except Exception:
                continue
        else:
            d = item
        dexes.append(d)

    for d in dexes:
        bundle.dex_count += 1

        with contextlib.suppress(Exception):
            bundle.strings.extend(d.get_strings())

        try:
            for cls in d.get_classes():
                name = cls.get_name()
                if name:
                    bundle.classes.append(name)
                    for method in cls.get_methods():
                        mname = method.get_name()
                        if mname:
                            bundle.methods.append((name, mname))
        except Exception:
            # Fall back to the flat method table if class walking fails.
            try:
                for m in d.get_methods():
                    cname = m.get_class_name()
                    mname = m.get_name()
                    if cname and mname:
                        bundle.methods.append((cname, mname))
            except Exception:
                continue

    if bundle.dex_count == 0:
        raise DexUnavailable("APK contains no DEX bytecode.")

    bundle.strings = sorted(set(bundle.strings))
    bundle.classes = sorted(set(bundle.classes))
    bundle.methods = sorted(set(bundle.methods))
    return bundle


def _load_native_libs(path: Path) -> dict[str, dict[str, Any]]:
    """Map native library name -> metadata, from entries under lib/."""
    out: dict[str, dict[str, Any]] = {}
    with zipfile.ZipFile(path, "r") as zf:
        for info in zf.infolist():
            if not info.filename.startswith("lib/"):
                continue
            parts = info.filename.split("/")
            if len(parts) < 3:
                continue
            abi = parts[1]
            lib_name = parts[-1]
            entry = out.setdefault(
                lib_name,
                {"abis": [], "size_bytes": 0, "compressed_bytes": 0},
            )
            if abi not in entry["abis"]:
                entry["abis"].append(abi)
            entry["size_bytes"] += info.file_size
            entry["compressed_bytes"] += info.compress_size
    return out


def load_apk(path: str | Path) -> LoadedApk:
    """Validate and parse an APK from disk.

    Raises
    ------
    ApkNotFound
        Path is missing, not a ZIP, or lacks AndroidManifest.xml.
    DexUnavailable
        The APK parsed but no DEX could be read (common with packed apps).
    """
    p = Path(path)
    if not p.is_file():
        raise ApkNotFound(f"No such file: {p}")

    # androguard is extremely chatty. Silence it before it parses anything.
    configure_logging()

    if not zipfile.is_zipfile(p):
        raise ApkNotFound(f"Not a valid ZIP/APK: {p.name}")

    with zipfile.ZipFile(p, "r") as zf:
        names = set(zf.namelist())
        missing = [e for e in _REQUIRED_ENTRIES if e not in names]
        if missing:
            raise ApkNotFound(
                f"{p.name} is not an Android APK (missing {', '.join(missing)})."
            )

    try:
        apk = APK(str(p))
    except Exception as exc:
        raise ApkNotFound(f"Could not parse APK: {exc}") from exc

    return LoadedApk(
        path=p,
        apk=apk,
        sha256=sha256_of(p),
        size_bytes=p.stat().st_size,
        dex=_load_dex(apk),
        native_libs=_load_native_libs(p),
    )
