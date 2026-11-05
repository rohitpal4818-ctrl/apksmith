"""Cross-reference analysis: which methods reference which string literals.

The static analysers in :mod:`apksmith.analyze.code` work off the DEX string
pool, which only proves a value *exists* in the binary. This module goes one
step further and records, for each string, the methods whose bytecode actually
loads it with ``const-string``. That is still not a control-flow proof -- a
method may load a string on a path that never executes -- but it narrows
"a string exists somewhere in this APK" to "these specific methods touch it",
which is what makes a finding actionable.
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field
from typing import Any

from ..ingest.apkfile import LoadedApk


@dataclass
class XrefIndex:
    """A bidirectional map between string literals and the methods that load them."""

    #: String literal -> methods that load it, as ``(class_name, method_name)``.
    string_to_methods: dict[str, list[tuple[str, str]]] = field(default_factory=dict)
    #: ``(class_name, method_name)`` -> set of string literals it loads.
    method_to_strings: dict[tuple[str, str], set[str]] = field(default_factory=dict)

    def owners_of(self, value: str) -> list[tuple[str, str]]:
        """Methods that load ``value`` (exact, then substring, match).

        Returns a de-duplicated list in the order the methods were first seen.
        """
        if value in self.string_to_methods:
            candidates = self.string_to_methods[value]
        else:
            candidates = []
            for literal, methods in self.string_to_methods.items():
                if value in literal:
                    candidates.extend(methods)

        seen: set[tuple[str, str]] = set()
        result: list[tuple[str, str]] = []
        for pair in candidates:
            if pair not in seen:
                seen.add(pair)
                result.append(pair)
        return result

    def strings_of(self, class_name: str, method_name: str) -> set[str]:
        """String literals loaded by a single method."""
        return set(self.method_to_strings.get((class_name, method_name), ()))


def build_xref_index(loaded: LoadedApk) -> XrefIndex:
    """Walk every DEX method and record its ``const-string`` references.

    Methods without bytecode (abstract, native, or stripped) contribute
    nothing. A method that loads no strings contributes nothing. The index
    is built from the same DEX already parsed by :func:`load_apk`, so no
    additional I/O or tooling is required.
    """
    index = XrefIndex()
    string_to_methods: dict[str, list[tuple[str, str]]] = defaultdict(list)
    method_to_strings: dict[tuple[str, str], set[str]] = {}

    dexes = _dex_objects(loaded.apk)
    for dex in dexes:
        for cls in _safe_iter(dex.get_classes()):
            class_name = _name(cls.get_name())
            if not class_name:
                continue
            for method in _safe_iter(cls.get_methods()):
                method_name = _name(method.get_name())
                if not method_name:
                    continue
                code = _get_code(method)
                if code is None:
                    continue
                literals = _const_strings(code)
                if not literals:
                    continue
                key = (class_name, method_name)
                method_to_strings[key] = literals
                for literal in literals:
                    string_to_methods[literal].append(key)

    index.string_to_methods = dict(string_to_methods.items())
    index.method_to_strings = method_to_strings
    return index


def _dex_objects(apk: Any) -> list[Any]:
    raw = list(apk.get_all_dex())
    out: list[Any] = []
    for item in raw:
        if isinstance(item, (bytes, bytearray)):
            try:
                from androguard.core.dex import DEX

                out.append(DEX(bytes(item)))
            except Exception:
                continue
        else:
            out.append(item)
    return out


def _safe_iter(value: Any) -> list[Any]:
    try:
        return list(value)
    except Exception:
        return []


def _name(value: Any) -> str:
    if value is None:
        return ""
    return str(value)


def _get_code(method: Any) -> Any:
    try:
        return method.get_code()
    except Exception:
        return None


def _const_strings(code: Any) -> set[str]:
    literals: set[str] = set()
    try:
        bc = code.get_bc()
    except Exception:
        return literals
    try:
        instructions = list(bc.get_instructions())
    except Exception:
        return literals
    for ins in instructions:
        try:
            if "const-string" not in str(ins).lower():
                continue
            value = ins.get_string()
        except Exception:
            continue
        if isinstance(value, str) and value:
            literals.add(value)
    return literals
