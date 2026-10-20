"""
End-to-end pipeline tests.

M2 is the only stage that needs a model, which historically meant it was the
only stage nobody could test. These tests close that gap with a stub client
that returns canned JSON, so the whole chain is exercised without a key or a
network call:

    extract -> rank -> select -> chunk -> prompt -> parse -> merge -> synthesise

The stub deliberately returns *imperfect* output: fenced JSON, trailing commas,
duplicated screens, and a markdown-wrapped final response. If the pipeline can
survive that, it can survive a free model.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from apksmith.models import AppIdentity, Component, RiskReport
from apksmith.understand.llm import LlmStats
from apksmith.understand.pipeline import resolve_app_prefixes, understand
from apksmith.understand.spec import BehaviourSpec

# --------------------------------------------------------------------------- #
# A synthetic decompiled tree, so no jadx run is needed
# --------------------------------------------------------------------------- #
SCREEN_JAVA = """\
package com.example.ledgerly;

import androidx.activity.ComponentActivity;

public class ExpenseListScreen extends ComponentActivity {
    private final ExpenseRepository repository;

    public void onCreate(Bundle state) {
        repository.loadAll();
        setContentView(buildLayout());
    }

    public void onDeleteExpense(String id) {
        repository.delete(id);
    }
}
"""

REPO_JAVA = """\
package com.example.ledgerly;

public class ExpenseRepository {
    private final ApiService api;

    public void loadAll() {
        api.get("https://api.example.test/v1/expenses");
    }

    public void delete(String id) {
        api.delete("https://api.example.test/v1/expenses/" + id);
    }
}
"""

MODEL_JAVA = """\
package com.example.ledgerly.data;

public class ExpenseModel {
    public String id;
    public String category;
    public double amount;
}
"""

HILT_JAVA = """\
package com.example.ledgerly;

public class Hilt_ExpenseListScreen extends ComponentActivity {
    private Object componentManager;
}
"""

SYNTHETIC_JAVA = """\
package com.example.ledgerly;

public class ExpenseListScreen$$ExternalSyntheticLambda1 {
    public void invoke(Object o) { helper(o); }
}
"""


@pytest.fixture(scope="module")
def decompiled_tree(tmp_path_factory) -> Path:
    """A jadx-shaped output tree: <root>/sources/<package path>/<Class>.java."""
    root = tmp_path_factory.mktemp("jadx")
    sources = root / "sources"

    app = sources / "com" / "example" / "ledgerly"
    app.mkdir(parents=True)
    (app / "ExpenseListScreen.java").write_text(SCREEN_JAVA, encoding="utf-8")
    (app / "ExpenseRepository.java").write_text(REPO_JAVA, encoding="utf-8")
    (app / "ExpenseModel.java").write_text(MODEL_JAVA, encoding="utf-8")
    (app / "Hilt_ExpenseListScreen.java").write_text(HILT_JAVA, encoding="utf-8")
    (app / "ExpenseListScreen$$ExternalSyntheticLambda1.java").write_text(
        SYNTHETIC_JAVA, encoding="utf-8"
    )

    # Third-party noise that must never reach the model.
    noise = sources / "okhttp3"
    noise.mkdir(parents=True)
    (noise / "OkHttpClient.java").write_text(
        "package okhttp3;\npublic class OkHttpClient {\n"
        "    public void connect() { }\n}\n",
        encoding="utf-8",
    )
    return root


def _report() -> RiskReport:
    return RiskReport(
        identity=AppIdentity(
            package="com.example.ledgerly",
            app_name="Ledgerly",
            version_name="1.0",
            min_sdk=24,
            target_sdk=34,
            main_activity="com.example.ledgerly.ExpenseListScreen",
        ),
        components=[
            Component(kind="activity", name="com.example.ledgerly.ExpenseListScreen"),
        ],
        endpoints=[
            {
                "value": "https://api.example.test/v1/expenses",
                "scheme": "https",
                "host": "api.example.test",
                "path": "/v1/expenses",
                "source": "code",
                "confidence": "high",
            }
        ],
    )


# --------------------------------------------------------------------------- #
# Stub client
# --------------------------------------------------------------------------- #
PARTIAL = {
    "purpose_hint": "tracks expenses",
    "screens": [
        {
            "name": "Expense List",
            "purpose": "See and delete expenses",
            "shows": ["expense rows", "total"],
            "actions": ["delete an expense"],
            "evidence": ["ExpenseListScreen"],
            "confidence": "high",
        }
    ],
    "features": [{"name": "Delete an expense", "description": "", "implemented": True}],
    "data_stored": [{"name": "expenses", "kind": "database", "description": ""}],
    "network_calls": [
        {
            "purpose": "fetch expenses",
            "endpoint": "https://api.example.test/v1/expenses",
            "method": "GET",
            "evidence": ["ExpenseRepository"],
        }
    ],
    "platform_dependencies": [],
    "caveats": ["static analysis only"],
}

FINAL = {
    "app_name": "Ledgerly",
    "package": "com.example.ledgerly",
    "purpose": "An expense tracker for people who want a simple running total.",
    "target_users": "People who want a plain expense log.",
    "screens": [
        {
            "name": "Expense List",
            "purpose": "See and delete expenses",
            "shows": ["rows", "total"],
            "actions": ["delete"],
            "evidence": ["ExpenseListScreen"],
            "confidence": "high",
        }
    ],
    "features": [{"name": "Delete an expense", "description": "", "implemented": True}],
    "data_stored": [{"name": "expenses", "kind": "database", "description": ""}],
    "network_calls": [
        {
            "purpose": "fetch",
            "endpoint": "https://api.example.test/v1/expenses",
            "method": "GET",
            "evidence": ["ExpenseRepository"],
        }
    ],
    "permissions_justified": {"android.permission.INTERNET": "fetches expenses"},
    "platform_dependencies": [],
    "caveats": ["static analysis only"],
}


class StubClient:
    """Stands in for LlmClient. Mimics a small free model's misbehaviour."""

    def __init__(self, style: str = "fenced") -> None:
        self.style = style
        self.api_key = "stub"
        self.model = "stub"
        self.cache_dir = Path(".stub-cache")
        self.stats = LlmStats()
        self.prompts: list[str] = []
        self.systems: list[str] = []

    def complete(self, system, user, **kwargs) -> str:
        self.prompts.append(user)
        self.systems.append(system)
        self.stats.requests += 1

        is_synthesis = "Merge these" in user
        payload = FINAL if is_synthesis else PARTIAL
        body = json.dumps(payload)

        if self.style == "fenced":
            # Markdown fence, prose either side, and a trailing comma before
            # the closing brace -- the classic sloppy-model output. Note the
            # final `}` is kept: removing it would be unrecoverable garbage
            # rather than something a parser should have to tolerate.
            sloppy = body[:-1] + ",}"
            return f"Here is the JSON you asked for:\n```json\n{sloppy}\n```\nHope this helps."
        if self.style == "prose":
            return f"Sure! Based on the classes provided:\n{body}\nLet me know if you need more."
        if self.style == "empty":
            return ""
        raise AssertionError(f"unknown style {self.style}")


# --------------------------------------------------------------------------- #
# Tests
# --------------------------------------------------------------------------- #
def test_resolve_finds_package_from_entry_point(decompiled_tree: Path):
    assert resolve_app_prefixes(_report(), decompiled_tree, min_classes=2) == [
        "com/example/ledgerly"
    ]


@pytest.mark.parametrize("style", ["fenced", "prose"])
def test_pipeline_runs_end_to_end(decompiled_tree: Path, style: str):
    """The whole chain, with awkward-but-valid model output."""
    client = StubClient(style=style)
    result = understand(
        _report(),
        decompiled_tree,
        client,  # type: ignore[arg-type]
        max_classes=12,
        per_chunk=3,
    )

    spec = result.spec
    assert isinstance(spec, BehaviourSpec)
    assert spec.package == "com.example.ledgerly"
    assert spec.purpose.startswith("An expense tracker")
    assert [s.name for s in spec.screens] == ["Expense List"]
    assert spec.network_calls[0].endpoint == "https://api.example.test/v1/expenses"
    assert result.classes_sent >= 2
    assert result.parts >= 1


def test_pipeline_survives_empty_model_output(decompiled_tree: Path):
    """A model that returns nothing must fail loudly, not silently succeed."""
    from apksmith.understand.pipeline import UnderstandingFailed

    client = StubClient(style="empty")
    with pytest.raises(UnderstandingFailed):
        understand(
            _report(),
            decompiled_tree,
            client,  # type: ignore[arg-type]
            max_classes=12,
            per_chunk=3,
        )


def test_third_party_code_never_reaches_the_prompt(decompiled_tree: Path):
    """OkHttp's source must not be billed to the model."""
    client = StubClient()
    understand(
        _report(),
        decompiled_tree,
        client,  # type: ignore[arg-type]
        max_classes=12,
        per_chunk=3,
    )
    for prompt in client.prompts:
        assert "OkHttpClient" not in prompt
        assert "okhttp3" not in prompt


def test_synthetic_classes_never_reach_the_prompt(decompiled_tree: Path):
    client = StubClient()
    understand(
        _report(),
        decompiled_tree,
        client,  # type: ignore[arg-type]
        max_classes=12,
        per_chunk=3,
    )
    for prompt in client.prompts:
        assert "ExternalSyntheticLambda" not in prompt


def test_static_facts_are_in_the_prompt(decompiled_tree: Path):
    """Endpoints found by M1 are ground truth and must be offered to the model."""
    client = StubClient()
    understand(
        _report(),
        decompiled_tree,
        client,  # type: ignore[arg-type]
        max_classes=12,
        per_chunk=3,
    )
    assert "api.example.test" in client.prompts[0]


def test_synthesis_asks_for_a_merge_not_another_extraction(decompiled_tree: Path):
    client = StubClient()
    understand(
        _report(),
        decompiled_tree,
        client,  # type: ignore[arg-type]
        max_classes=12,
        per_chunk=3,
    )
    assert len(client.systems) >= 2
    assert "merging" in client.systems[-1].lower()


def test_no_api_key_fails_with_a_clear_message(decompiled_tree: Path):
    from apksmith.understand.llm import LlmClient, LlmUnavailable

    client = LlmClient(api_key=None)
    client.api_key = None
    with pytest.raises(LlmUnavailable, match="openrouter"):
        client.complete(system="s", user="u")


def test_generated_project_from_pipeline_spec(decompiled_tree: Path, tmp_path: Path):
    """M2 output must be directly consumable by M3."""
    from apksmith.generate import build_flutter_project

    result = understand(
        _report(),
        decompiled_tree,
        StubClient(),  # type: ignore[arg-type]
        max_classes=12,
        per_chunk=3,
    )
    generated = build_flutter_project(result.spec)
    written = generated.write(tmp_path, overwrite=True)

    assert written, "nothing generated"
    assert (tmp_path / "pubspec.yaml").exists()
    assert (tmp_path / "lib/router.dart").exists()
    # The screen named by the stub must have produced a file.
    assert (tmp_path / "lib/screens/expense_list_screen.dart").exists()
