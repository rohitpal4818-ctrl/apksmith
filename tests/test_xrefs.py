"""Tests for DEX-level cross-reference analysis."""

from __future__ import annotations

from pathlib import Path

import pytest

from apksmith.analyze.xrefs import XrefIndex, build_xref_index

SAMPLE_APK = Path(__file__).resolve().parents[1] / "samples" / "F-Droid.apk"
needs_apk = pytest.mark.skipif(
    not SAMPLE_APK.exists(),
    reason="sample APK not fetched; run scripts/fetch_samples.sh",
)


def test_owners_of_exact_match():
    """An exact string hit returns its methods without substring scanning."""
    index = XrefIndex()
    index.string_to_methods = {"https://example.com/api": [("Lcom/Foo;", "bar")]}
    index.method_to_strings = {("Lcom/Foo;", "bar"): {"https://example.com/api"}}
    assert index.owners_of("https://example.com/api") == [("Lcom/Foo;", "bar")]


def test_owners_of_substring_fallback():
    """A value not present verbatim still resolves via substring."""
    index = XrefIndex()
    index.string_to_methods = {
        "prefix https://example.com/api suffix": [("Lcom/Foo;", "bar")]
    }
    assert index.owners_of("https://example.com/api") == [("Lcom/Foo;", "bar")]


def test_owners_of_deduplicates():
    """The same method appearing twice is reported once."""
    index = XrefIndex()
    index.string_to_methods = {
        "a": [("Lcom/Foo;", "bar"), ("Lcom/Foo;", "bar")],
    }
    assert index.owners_of("a") == [("Lcom/Foo;", "bar")]


def test_strings_of_unknown_method_is_empty():
    index = XrefIndex()
    assert index.strings_of("Lnope;", "missing") == set()


@needs_apk
def test_build_xref_index_against_real_apk():
    """Cross-references must be recoverable from a real DEX without jadx."""
    from apksmith.ingest.apkfile import load_apk

    loaded = load_apk(SAMPLE_APK)
    index = build_xref_index(loaded)
    # A real app references many distinct strings.
    assert len(index.string_to_methods) > 100
    assert len(index.method_to_strings) > 100
    # Every recorded method must own at least one of its listed strings.
    for (cls, method), strings in list(index.method_to_strings.items())[:10]:
        for s in strings:
            assert (cls, method) in index.string_to_methods[s]
