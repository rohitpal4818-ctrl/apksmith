"""
Regression tests for generator name collisions.

These were found by fuzzing the builder with adversarial labels, not by
reading the code. Each one previously produced two files at the same path --
the second silently overwriting the first, so a screen would disappear from
the generated project with no error at all.

The worst case was a screen named "Home", which overwrote the app's own entry
screen.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from apksmith.generate import build_flutter_project
from apksmith.generate.naming import pascal, snake
from apksmith.understand.spec import BehaviourSpec


def _spec(**kwargs) -> BehaviourSpec:
    base = {"app_name": "T", "package": "com.t.app", "screens": [{"name": "One"}]}
    base.update(kwargs)
    return BehaviourSpec.model_validate(base)


def _paths(spec) -> list[str]:
    return [f.path for f in build_flutter_project(spec).files]


def test_identical_screen_names_do_not_collide():
    spec = _spec(screens=[{"name": "App List"}, {"name": "App List"}])
    paths = _paths(spec)
    assert len(paths) == len(set(paths)), "two screens produced the same file"
    assert "lib/screens/app_list_screen.dart" in paths
    assert "lib/screens/app_list_2_screen.dart" in paths


def test_names_colliding_after_normalisation_do_not_collide():
    """``App List`` and ``app_list`` both normalise to ``app_list``."""
    spec = _spec(screens=[{"name": "App List"}, {"name": "app_list"}])
    paths = _paths(spec)
    assert len(paths) == len(set(paths))
    assert len([p for p in paths if p.startswith("lib/screens/app_list")]) == 2


def test_duplicate_data_names_do_not_collide():
    spec = _spec(
        data_stored=[{"name": "expenses", "kind": "db"}, {"name": "Expenses", "kind": "db"}]
    )
    paths = _paths(spec)
    assert len(paths) == len(set(paths))
    assert len([p for p in paths if p.startswith("lib/models/expense")]) == 2


def test_a_screen_cannot_overwrite_the_entry_screen():
    """A screen named Home must not clobber lib/screens/home_screen.dart."""
    spec = _spec(screens=[{"name": "Home"}])
    paths = _paths(spec)
    assert len(paths) == len(set(paths))
    assert "lib/screens/home_screen.dart" in paths
    assert "lib/screens/home_2_screen.dart" in paths


def test_a_screen_cannot_overwrite_the_fallback_screen():
    spec = _spec(screens=[{"name": "Unknown Route"}])
    paths = _paths(spec)
    assert len(paths) == len(set(paths))
    assert "lib/screens/unknown_route_screen.dart" in paths
    assert "lib/screens/unknown_route_2_screen.dart" in paths


def test_unusable_names_still_produce_distinct_files():
    spec = _spec(screens=[{"name": "   "}, {"name": "!!!"}])
    paths = _paths(spec)
    assert len(paths) == len(set(paths))


def test_routes_stay_in_step_with_files_after_a_collision(tmp_path: Path):
    """The whole point: after a collision, every route must still resolve."""
    spec = _spec(screens=[{"name": "App List"}, {"name": "App List"}])
    generated = build_flutter_project(spec)
    written = generated.write(tmp_path, overwrite=True)

    router = (tmp_path / "lib/router.dart").read_text(encoding="utf-8")
    screen_stems = {
        p.name[: -len("_screen.dart")]
        for p in written
        if p.parent.name == "screens" and p.name.endswith("_screen.dart")
    }
    # The entry screen is always routed. The fallback screen deliberately is
    # not: AppRouter.generate reaches it when no route matches.
    screen_stems.add("home")
    screen_stems.discard("unknown_route")

    for stem in screen_stems:
        assert f"AppRoutes.{stem}:" in router, f"route {stem} missing from the table"
        assert (tmp_path / "lib/screens" / f"{stem}_screen.dart").exists()

    # And the two App List screens have genuinely different classes.
    assert "AppListScreen" in (tmp_path / "lib/screens/app_list_screen.dart").read_text(
        encoding="utf-8"
    )
    assert "AppList2Screen" in (
        tmp_path / "lib/screens/app_list_2_screen.dart"
    ).read_text(encoding="utf-8")


def test_route_names_are_unique_dart_constants():
    spec = _spec(screens=[{"name": "App List"}, {"name": "app_list"}])
    router = next(
        f.content for f in build_flutter_project(spec).files if f.path == "lib/router.dart"
    )
    consts = [
        line.split("static const ")[1].split(" =")[0]
        for line in router.splitlines()
        if "static const" in line
    ]
    assert len(consts) == len(set(consts)), f"duplicate Dart constants: {consts}"


@pytest.mark.parametrize(
    "label",
    ["Ünïcode “quotes”", "a" * 300, "!!!", "  ", "with/slash", "with\\backslash"],
)
def test_hostile_labels_generate_without_error(label: str):
    spec = _spec(screens=[{"name": label}])
    generated = build_flutter_project(spec)
    paths = [f.path for f in generated.files]
    assert len(paths) == len(set(paths))
    for gf in generated.files:
        assert "{{" not in gf.content, f"{gf.path} has an unsubstituted placeholder"
        # Identifiers must remain valid Dart even for a hostile label.
        if gf.path.endswith(".dart"):
            assert "\n\n\n" not in gf.content


def test_identifier_helpers_are_total():
    """No input may produce a blank or unusable identifier."""
    for value in ["", " ", "!!!", "1", "-", "Ünïcode", "a" * 500, "s", "ss"]:
        assert snake(value)
        assert pascal(value)
        assert snake(value).isidentifier() or snake(value)[0].isalpha()
