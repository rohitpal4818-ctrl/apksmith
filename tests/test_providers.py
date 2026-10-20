"""Provider routing for the M2 LLM client.

The client speaks one wire format but two backends. Three things have to stay
true, because getting any of them wrong silently bills the wrong account or
serves a stale answer:

1. Each provider hits its own endpoint with its own default model.
2. Each provider reads its own environment variable.
3. The response cache is keyed by provider, so a Groq answer is never replayed
   for an OpenRouter request with the same prompt.

Also covering a real bug: ``_cache_put`` used ``contextlib.suppress`` without
importing ``contextlib``, and no existing test ever wrote to the cache, so the
NameError only surfaced on the first live API call.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from apksmith.understand.llm import (
    DEFAULT_MODEL,
    ENDPOINTS,
    LlmClient,
    LlmUnavailable,
    known_providers,
    parse_json_loose,
)


class FakeResponse:
    """Minimal stand-in for ``requests.Response``."""

    def __init__(self, status_code=200, payload=None, text="", headers=None):
        self.status_code = status_code
        self._payload = payload if payload is not None else {}
        self.text = text or json.dumps(self._payload)
        self.headers = headers or {}

    def json(self):
        return self._payload

    def raise_for_status(self):
        if self.status_code >= 400:
            raise AssertionError("should not be called for error statuses")


def ok_response(content: str = '{"purpose": "test"}') -> FakeResponse:
    return FakeResponse(
        payload={
            "choices": [{"message": {"content": content}}],
            "usage": {"prompt_tokens": 11, "completion_tokens": 7},
        }
    )


@pytest.fixture
def calls(monkeypatch):
    """Capture every outbound request instead of hitting the network."""
    recorded: list[dict] = []

    def fake_post(url, headers=None, json=None, timeout=None, **kwargs):
        recorded.append({"url": url, "headers": headers, "json": json})
        return ok_response()

    monkeypatch.setattr("requests.post", fake_post)
    # Never sleep for real in tests.
    monkeypatch.setattr(LlmClient, "_sleep", staticmethod(lambda *a, **k: None))
    return recorded


# --------------------------------------------------------------------------- #
# Registration and defaults
# --------------------------------------------------------------------------- #
def test_both_providers_are_registered():
    assert known_providers() == ["groq", "openrouter"]


@pytest.mark.parametrize("provider", ["openrouter", "groq"])
def test_each_provider_has_a_default_model(provider):
    client = LlmClient(api_key="k", provider=provider)
    assert client.model == DEFAULT_MODEL[provider]
    assert client.stats.model == DEFAULT_MODEL[provider]
    assert client.stats.provider == provider


def test_groq_default_is_gpt_oss_120b():
    """Groq retired Llama 3.3 70B from the free tier in August 2026."""
    assert DEFAULT_MODEL["groq"] == "openai/gpt-oss-120b"


def test_openrouter_remains_the_default_provider():
    assert LlmClient(api_key="k").provider == "openrouter"


def test_unknown_provider_is_rejected():
    with pytest.raises(LlmUnavailable) as excinfo:
        LlmClient(api_key="k", provider="anthropic")
    assert "Unknown provider" in str(excinfo.value)
    assert "groq" in str(excinfo.value)


def test_explicit_model_overrides_the_default():
    client = LlmClient(api_key="k", provider="groq", model="openai/gpt-oss-20b")
    assert client.model == "openai/gpt-oss-20b"


# --------------------------------------------------------------------------- #
# Endpoints and headers
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize("provider", ["openrouter", "groq"])
def test_request_goes_to_the_provider_endpoint(provider, calls, tmp_path):
    client = LlmClient(api_key="secret", provider=provider, cache_dir=tmp_path)
    client.complete("sys", "user")
    assert calls[0]["url"] == ENDPOINTS[provider]


@pytest.mark.parametrize("provider", ["openrouter", "groq"])
def test_bearer_token_is_sent(provider, calls, tmp_path):
    LlmClient(api_key="secret", provider=provider, cache_dir=tmp_path).complete("sys", "user")
    assert calls[0]["headers"]["Authorization"] == "Bearer secret"


def test_openrouter_carries_attribution_headers(calls, tmp_path):
    LlmClient(api_key="k", provider="openrouter", cache_dir=tmp_path).complete("s", "u")
    assert "HTTP-Referer" in calls[0]["headers"]


def test_groq_does_not_send_openrouter_headers(calls, tmp_path):
    """Groq rejects unknown headers on some gateways; keep its request clean."""
    LlmClient(api_key="k", provider="groq", cache_dir=tmp_path).complete("s", "u")
    assert "HTTP-Referer" not in calls[0]["headers"]


@pytest.mark.parametrize("provider", ["openrouter", "groq"])
def test_json_mode_is_requested(provider, calls, tmp_path):
    LlmClient(api_key="k", provider=provider, cache_dir=tmp_path).complete("s", "u")
    assert calls[0]["json"]["response_format"] == {"type": "json_object"}


# --------------------------------------------------------------------------- #
# Environment variables
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize(
    "provider, env_name",
    [("openrouter", "OPENROUTER_API_KEY"), ("groq", "GROQ_API_KEY")],
)
def test_each_provider_reads_its_own_env_var(monkeypatch, provider, env_name):
    monkeypatch.setenv(env_name, "from-env")
    assert LlmClient(provider=provider).api_key == "from-env"


def test_groq_does_not_fall_back_to_the_openrouter_key(monkeypatch):
    monkeypatch.delenv("GROQ_API_KEY", raising=False)
    monkeypatch.setenv("OPENROUTER_API_KEY", "sk-or-v1-present")
    assert LlmClient(provider="groq").api_key is None


def test_missing_key_names_the_right_env_var_and_portal(monkeypatch):
    monkeypatch.delenv("GROQ_API_KEY", raising=False)
    with pytest.raises(LlmUnavailable) as excinfo:
        LlmClient(provider="groq").complete("s", "u")
    message = str(excinfo.value)
    assert "GROQ_API_KEY" in message
    assert "console.groq.com" in message


# --------------------------------------------------------------------------- #
# Caching
# --------------------------------------------------------------------------- #
def test_cache_write_and_read_roundtrip(tmp_path):
    """Regression: _cache_put referenced contextlib without importing it."""
    client = LlmClient(api_key="k", provider="groq", cache_dir=tmp_path)
    client._cache_put("some key", '{"a": 1}')
    assert client._cache_get("some key") == '{"a": 1}'
    assert client._cache_get("absent") is None


def test_cache_is_keyed_by_provider(tmp_path, monkeypatch):
    """The same prompt on two providers must not share a cached answer."""
    monkeypatch.setattr(
        "requests.post",
        lambda *a, **k: ok_response('{"from": "network"}'),
    )
    monkeypatch.setattr(LlmClient, "_sleep", staticmethod(lambda *a, **k: None))

    groq = LlmClient(api_key="k", provider="groq", cache_dir=tmp_path)
    groq.complete("sys", "same user prompt")

    # Same prompt, same cache dir, different provider: must not be served.
    orouter = LlmClient(api_key="k", provider="openrouter", cache_dir=tmp_path)
    orouter.complete("sys", "same user prompt")

    assert groq.stats.cached == 0
    assert orouter.stats.cached == 0


def test_cache_hit_avoids_a_second_network_call(tmp_path, calls):
    client = LlmClient(api_key="k", provider="groq", cache_dir=tmp_path)
    client.complete("sys", "user")
    client.complete("sys", "user")
    assert len(calls) == 1
    assert client.stats.cached == 1
    assert client.stats.requests == 1


# --------------------------------------------------------------------------- #
# Stats
# --------------------------------------------------------------------------- #
def test_usage_is_accumulated(tmp_path, calls):
    client = LlmClient(api_key="k", provider="groq", cache_dir=tmp_path)
    client.complete("sys", "user")
    assert client.stats.prompt_tokens == 11
    assert client.stats.completion_tokens == 7
    assert client.stats.failures == 0


def test_stats_dict_names_the_provider():
    stats = LlmClient(api_key="k", provider="groq").stats.as_dict()
    assert stats["provider"] == "groq"
    assert stats["model"] == "openai/gpt-oss-120b"


# --------------------------------------------------------------------------- #
# Failure handling
# --------------------------------------------------------------------------- #
def test_rate_limit_mentions_the_providers_free_tier(tmp_path, monkeypatch):
    monkeypatch.setattr(
        "requests.post",
        lambda *a, **k: FakeResponse(status_code=429, text="slow down"),
    )
    monkeypatch.setattr(LlmClient, "_sleep", staticmethod(lambda *a, **k: None))

    client = LlmClient(api_key="k", provider="groq", cache_dir=tmp_path, max_retries=2)
    with pytest.raises(LlmUnavailable) as excinfo:
        client.complete("s", "u")
    assert "rate limited" in str(excinfo.value)
    assert "1,000" in str(excinfo.value)


def test_openrouter_rate_limit_mentions_its_own_numbers(tmp_path, monkeypatch):
    monkeypatch.setattr(
        "requests.post",
        lambda *a, **k: FakeResponse(status_code=429, text="slow down"),
    )
    monkeypatch.setattr(LlmClient, "_sleep", staticmethod(lambda *a, **k: None))

    client = LlmClient(
        api_key="k", provider="openrouter", cache_dir=tmp_path, max_retries=2
    )
    with pytest.raises(LlmUnavailable) as excinfo:
        client.complete("s", "u")
    assert "50" in str(excinfo.value)


def test_server_error_is_retried_then_raised(tmp_path, monkeypatch):
    attempts = {"n": 0}

    def flaky(*a, **k):
        attempts["n"] += 1
        return FakeResponse(status_code=503, text="upstream hiccup")

    monkeypatch.setattr("requests.post", flaky)
    monkeypatch.setattr(LlmClient, "_sleep", staticmethod(lambda *a, **k: None))

    client = LlmClient(api_key="k", provider="groq", cache_dir=tmp_path, max_retries=3)
    with pytest.raises(LlmUnavailable):
        client.complete("s", "u")
    assert attempts["n"] == 3


def test_malformed_response_body_is_not_cached(tmp_path, monkeypatch):
    monkeypatch.setattr(
        "requests.post", lambda *a, **k: FakeResponse(payload={"nope": True})
    )
    monkeypatch.setattr(LlmClient, "_sleep", staticmethod(lambda *a, **k: None))

    client = LlmClient(api_key="k", provider="groq", cache_dir=tmp_path, max_retries=1)
    with pytest.raises(LlmUnavailable):
        client.complete("s", "u")
    assert list(tmp_path.rglob("*.json")) == []


# --------------------------------------------------------------------------- #
# JSON salvage is provider-independent
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize(
    "raw",
    [
        '{"a": 1}',
        '```json\n{"a": 1}\n```',
        'Here you go:\n{"a": 1}\nHope that helps.',
        '{"a": 1,}',
    ],
)
def test_loose_json_parsing_survives_small_model_output(raw):
    assert parse_json_loose(raw) == {"a": 1}


def test_loose_json_rejects_non_objects():
    assert parse_json_loose("[1, 2, 3]") is None
    assert parse_json_loose("no json here") is None
