"""
Tests for M3 (generation), M5 (evaluation) and the MCP tool surface.

The generation tests deliberately assert *Dart correctness* properties rather
than exact text, because a generated project that does not compile is the one
failure mode that makes the whole tool useless.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

from apksmith.evaluate import SuiteReport, evaluate, load_suite
from apksmith.generate import build_flutter_project
from apksmith.generate.naming import (
    GeneratedFile,
    GenerationResult,
    dart_string,
    pascal,
    singular,
    snake,
)
from apksmith.understand.spec import BehaviourSpec

SPEC = BehaviourSpec.model_validate(
    {
        "app_name": "Ledgerly",
        "package": "com.example.ledgerly",
        "purpose": "A simple expense tracker.",
        "screens": [
            {
                "name": "Expense List",
                "purpose": "See expenses",
                "shows": ["rows", "total"],
                "actions": ["add"],
                "evidence": ["ExpenseListActivity"],
                "confidence": "high",
            },
            {
                "name": "Add Expense",
                "purpose": "Record one",
                "shows": ["amount field"],
                "evidence": ["AddExpenseActivity"],
                "confidence": "low",
            },
        ],
        "features": [
            {"name": "Monthly total", "description": "", "implemented": True},
            {"name": "Charts", "description": "", "implemented": False},
        ],
        "data_stored": [{"name": "expenses", "kind": "database", "description": ""}],
        "network_calls": [
            {
                "purpose": "backup",
                "endpoint": "https://api.test/v1",
                "method": "POST",
                "evidence": ["BackupService"],
            }
        ],
        "permissions_justified": {"android.permission.INTERNET": "backups"},
    }
)


# --------------------------------------------------------------------------- #
# Naming
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize(
    "raw,expected",
    [
        ("Expense List", "expense_list"),
        ("addExpense", "add_expense"),
        ("HTTPS Connection", "https_connection"),
        ("Settings", "settings"),
        ("already_snake", "already_snake"),
        ("2024 Report", "v_2024_report"),
        ("!!!", "item"),
    ],
)
def test_snake(raw, expected):
    assert snake(raw) == expected


@pytest.mark.parametrize(
    "raw,expected",
    [
        ("expenses", "expense"),
        ("categories", "category"),
        ("settings", "setting"),
        ("address", "address"),
        ("items", "item"),
        ("", "item"),
    ],
)
def test_singular(raw, expected):
    assert singular(raw) == expected


def test_singular_never_returns_empty():
    """A generated identifier must never be blank, whatever the input."""
    for value in ["", "s", "ss", "!!!", "ies", "1", "  "]:
        assert singular(value)
        assert pascal(value)
        assert snake(value)


def test_pascal():
    assert pascal("expense list") == "ExpenseList"
    assert pascal("HTTPClient") == "Httpclient"


def test_dart_string_escapes():
    assert dart_string('say "hi"') == '"say \\"hi\\""'
    assert dart_string("cost $5") == '"cost \\$5"'
    assert dart_string("line\nbreak") == '"line\\nbreak"'


# --------------------------------------------------------------------------- #
# Generation
# --------------------------------------------------------------------------- #
@pytest.fixture(scope="module")
def generated() -> GenerationResult:
    return build_flutter_project(SPEC)


def test_generates_expected_scaffolding(generated: GenerationResult):
    paths = {f.path for f in generated.files}
    for required in (
        "pubspec.yaml",
        "lib/main.dart",
        "lib/app.dart",
        "lib/router.dart",
        "lib/theme.dart",
        "test/widget_test.dart",
        "README.md",
        "docs/SPEC.md",
    ):
        assert required in paths, f"missing {required}"


def test_one_file_per_screen(generated: GenerationResult):
    paths = {f.path for f in generated.files}
    assert "lib/screens/expense_list_screen.dart" in paths
    assert "lib/screens/add_expense_screen.dart" in paths


def test_every_route_has_a_screen_file(generated: GenerationResult):
    """A route pointing at a class with no source file would not compile."""
    router = next(f.content for f in generated.files if f.path == "lib/router.dart")
    screen_files = [f.path for f in generated.files if f.path.startswith("lib/screens/")]

    for class_name in re.findall(r"\(\_\) => const (\w+)\(\)", router):
        expected = f"lib/screens/{snake(class_name)}.dart"
        assert expected in screen_files, (
            f"route uses {class_name}, expected {expected} to exist"
        )


def test_no_unfilled_placeholders(generated: GenerationResult):
    """Every {{placeholder}} must be substituted."""
    for gf in generated.files:
        assert "{{" not in gf.content, f"{gf.path} has an unsubstituted placeholder"
        assert "}}" not in gf.content or gf.path.endswith(".md"), gf.path


def test_dart_braces_are_balanced(generated: GenerationResult):
    """Cheap proxy for syntactic validity."""
    for gf in generated.files:
        if not gf.path.endswith(".dart"):
            continue
        # Order matters: strip string literals *before* stripping comments. A
        # URL like "https://..." contains "//", so removing comments first
        # swallows the rest of the line, including any closing brace on it.
        stripped = re.sub(r'"(?:[^"\\\n]|\\.)*"', "@@", gf.content)
        stripped = re.sub(r"'(?:[^'\\\n]|\\.)*'", "@@", stripped)
        stripped = re.sub(r"//[^\n]*", "", stripped)
        assert stripped.count("{") == stripped.count("}"), (
            f"{gf.path} has unbalanced braces"
        )


def test_generated_files_carry_provenance(generated: GenerationResult):
    """Anything that could be mistaken for hand-written code says where it came from."""
    exempt = {".gitignore"}
    for gf in generated.files:
        if gf.path.endswith((".dart", ".yaml")) and gf.path not in exempt:
            assert "APKSMITH" in gf.content, f"{gf.path} has no provenance header"


def test_readme_states_what_is_not_real(generated: GenerationResult):
    readme = next(f.content for f in generated.files if f.path == "README.md")
    assert "scaffold" in readme.lower()
    assert "TODO" in readme
    assert "not observable statically" in readme.lower()


def test_low_confidence_surfaces_as_open_question(generated: GenerationResult):
    assert any("low-confidence" in q for q in generated.open_questions)


def test_stubbed_feature_surfaces_as_open_question(generated: GenerationResult):
    assert any("stubbed" in q for q in generated.open_questions)


def test_generation_works_with_no_api_key(generated: GenerationResult):
    """The builder must never require a model."""
    assert len(generated.files) > 8


def test_write_is_idempotent(tmp_path: Path, generated: GenerationResult):
    first = generated.write(tmp_path, overwrite=True)
    assert len(first) > 0
    second = generated.write(tmp_path, overwrite=False)
    assert second == [], "existing files must not be clobbered without --overwrite"
    third = generated.write(tmp_path, overwrite=True)
    assert len(third) == len(first)


def test_refuses_empty_spec():
    """Generating from nothing would produce an empty, useless project."""
    with pytest.raises(ValueError, match="nothing to generate"):
        build_flutter_project(BehaviourSpec(package="com.example.empty"))


def test_evidence_is_preserved_in_screen_source(generated: GenerationResult):
    screen = next(
        f.content
        for f in generated.files
        if f.path == "lib/screens/expense_list_screen.dart"
    )
    assert "ExpenseListActivity" in screen, "provenance lost"
    assert "TODO" in screen


# --------------------------------------------------------------------------- #
# Evaluation
# --------------------------------------------------------------------------- #
def test_perfect_match_scores_one():
    reference = {
        "purpose": "An expense tracker for people who want simple budgets.",
        "screens": ["Expense List", "Add Expense"],
        "features": ["Monthly total", "Charts"],
    }
    result = evaluate(SPEC, reference, app_name="perfect")
    assert result.mean_f1 > 0.9


def test_fuzzy_label_matching_tolerates_formatting():
    reference = {"screens": ["Expense List", "Add Expense"]}
    result = evaluate(SPEC, reference)
    lookup = {m.name: m.value for m in result.metrics}
    assert lookup["screens_recall"] == 1.0, "formatting should not defeat matching"


def test_invented_screens_lower_precision():
    inflated = SPEC.model_copy(deep=True)
    inflated.screens = inflated.screens + [
        {"name": "Admin Console", "purpose": "", "shows": [], "confidence": "low"}
    ]
    honest = evaluate(SPEC, {"screens": ["Expense List", "Add Expense"]})
    padded = evaluate(inflated, {"screens": ["Expense List", "Add Expense"]})
    h = {m.name: m.value for m in honest.metrics}
    p = {m.name: m.value for m in padded.metrics}
    assert p["screens_precision"] < h["screens_precision"]


def test_missed_screens_are_reported():
    result = evaluate(SPEC, {"screens": ["Home", "Export", "Backup Screen"]})
    assert any("not found" in n for n in result.notes)


def test_empty_reference_produces_no_score_not_a_crash():
    result = evaluate(SPEC, {})
    assert result.mean_f1 == 0.0
    assert any("nothing comparable" in n for n in result.notes)


def test_missing_purpose_is_flagged():
    bare = SPEC.model_copy(deep=True)
    bare.purpose = ""
    result = evaluate(bare, {"purpose": "does many things well"})
    assert any("No purpose" in n for n in result.notes)


def test_suite_report_renders():
    suite = SuiteReport(cases=[evaluate(SPEC, {"screens": ["Expense List"]}, "x")])
    md = suite.to_markdown()
    assert "evaluation report" in md.lower()
    assert "not truth" in md.lower(), "report must be honest about what it measures"
    assert "regression signal" in md.lower()


def test_load_bundled_suite_runs():
    suite_path = Path(__file__).resolve().parents[1] / "evaluation" / "suite.json"
    if not suite_path.is_file():
        pytest.skip("suite not present")
    suite = load_suite(suite_path)
    assert len(suite.cases) >= 2
    assert 0.0 <= suite.mean_f1 <= 1.0


def test_bundled_suite_references_are_not_model_output():
    """The suite must ship with a comment explaining provenance."""
    suite_path = Path(__file__).resolve().parents[1] / "evaluation" / "suite.json"
    data = json.loads(suite_path.read_text(encoding="utf-8"))
    assert "_comment" in data
    assert any("NOT derived from any model" in c for c in data["_comment"])


# --------------------------------------------------------------------------- #
# MCP surface
# --------------------------------------------------------------------------- #
def test_mcp_module_imports_without_sdk():
    """The MCP SDK is optional; importing must not break the CLI."""
    import apksmith.mcp_server as mcp_server

    assert hasattr(mcp_server, "build_server")
    assert "apk_analyse" in mcp_server.SERVER_INSTRUCTIONS
    assert mcp_server.HAVE_MCP in (True, False)


def test_mcp_tools_are_declared():
    import apksmith.mcp_server as mcp_server

    source = Path(mcp_server.__file__).read_text(encoding="utf-8")
    for tool in (
        "apk_identity",
        "apk_analyse",
        "apk_decompile",
        "apk_extract",
        "apk_understand",
        "apk_generate",
        "apk_coverage",
    ):
        assert f"def {tool}(" in source, f"tool {tool} missing"
    assert source.count("@mcp.tool()") >= 7
