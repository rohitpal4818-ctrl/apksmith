"""
Multi-provider LLM client for the understanding layer.

Providers
---------
``openrouter``
    Default. Broad model catalogue, but the free tier is 20 requests/minute
    and 50 requests/day without a one-time credit purchase.

``groq``
    Far more generous free tier: 30 requests/minute, 1,000 requests/day and
    200,000 tokens/day, with no card required. The model that matters is
    ``openai/gpt-oss-120b`` -- OpenAI's open-weight mixture-of-experts, which
    Groq recommends as the replacement for the Llama models it retired from
    the free tier in August 2026.

Three constraints shape this module, and they apply to every provider:

1. **Rate limits are real.** Both providers publish generous-looking limits
   that a large prompt can exhaust in one call, so every response carries its
   usage back to the caller and ``budget()`` reports what remains.

2. **Responses are cached by content hash.** Re-running on an unchanged APK
   must cost nothing. On a free tier this is the difference between being
   able to iterate and not.

3. **The model is not trusted.** Responses are parsed defensively, and a
   response that will not parse is retried with a repair prompt. Small models
   produce malformed JSON often enough that this is not optional.
"""

from __future__ import annotations

import contextlib
import hashlib
import json
import os
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import requests

from ..errors import ApkSmithError

#: Default model per provider.
DEFAULT_MODEL = {
    "openrouter": "nvidia/nemotron-3-ultra-550b-a55b:free",
    # Groq's replacement for the retired Llama 3.3 70B. Best available for
    # reasoning and code, which is what the understanding stage needs.
    "groq": "openai/gpt-oss-120b",
}

#: Groq's models are OpenAI-compatible, so the wire format matches.
ENDPOINTS = {
    "openrouter": "https://openrouter.ai/api/v1/chat/completions",
    "groq": "https://api.groq.com/openai/v1/chat/completions",
}

BUDGET_ENDPOINTS = {
    "openrouter": "https://openrouter.ai/api/v1/key",
}

#: Free-tier guidance, quoted when a 429 comes back. Being specific about the
#: numbers saves the user digging through documentation.
FREE_TIER_HELP = {
    "openrouter": (
        "The free tier allows 20 requests per minute and 50 per day. A one-time "
        "$10 credit purchase raises the daily limit to 1,000, permanently."
    ),
    "groq": (
        "Groq's free plan allows 30 requests per minute, 1,000 per day, and "
        "200,000 tokens per day. Whichever limit is reached first applies."
    ),
}


class LlmUnavailable(ApkSmithError):
    """No API key, or the provider could not be reached."""


def known_providers() -> list[str]:
    """Provider names the CLI will accept, sorted for stable ``--help`` text.

    Derived from the routing table rather than maintained as a second list, so
    adding a provider cannot leave the help text advertising a name that does
    not work.
    """
    return sorted(ENDPOINTS)


@dataclass
class LlmStats:
    """Token and request accounting, so a run can report its own cost."""

    requests: int = 0
    cached: int = 0
    prompt_tokens: int = 0
    completion_tokens: int = 0
    failures: int = 0
    retries: int = 0
    provider: str = "openrouter"
    model: str = ""

    def as_dict(self) -> dict[str, Any]:
        """Flat mapping for the CLI's run-stats block, in stable key order."""
        return {
            "provider": self.provider,
            "model": self.model,
            "requests": self.requests,
            "cached_responses": self.cached,
            "prompt_tokens": self.prompt_tokens,
            "completion_tokens": self.completion_tokens,
            "retries": self.retries,
            "failures": self.failures,
        }


@dataclass
class LlmClient:
    """Chat client with per-provider routing, disk caching and JSON salvage."""

    api_key: str | None = None
    model: str | None = None
    provider: str = "openrouter"
    cache_dir: Path = field(default_factory=lambda: Path(".apksmith-cache"))
    timeout: int = 120
    max_retries: int = 3
    stats: LlmStats = field(default_factory=LlmStats)

    def __post_init__(self) -> None:
        if self.provider not in ENDPOINTS:
            raise LlmUnavailable(
                f"Unknown provider {self.provider!r}. "
                f"Known providers: {', '.join(known_providers())}"
            )
        if self.model is None:
            self.model = DEFAULT_MODEL[self.provider]
        self.stats.provider = self.provider
        self.stats.model = self.model

        if self.api_key is None:
            env_name = {
                "openrouter": "OPENROUTER_API_KEY",
                "groq": "GROQ_API_KEY",
            }[self.provider]
            self.api_key = os.environ.get(env_name)

    # -- cache ------------------------------------------------------------ #
    def _cache_path(self, key: str) -> Path:
        # Two-level fan-out keeps directories small over a long project.
        digest = hashlib.sha256(key.encode("utf-8")).hexdigest()
        return self.cache_dir / digest[:2] / f"{digest}.json"

    def _cache_get(self, key: str) -> str | None:
        path = self._cache_path(key)
        if path.is_file():
            try:
                return json.loads(path.read_text(encoding="utf-8"))["content"]
            except (OSError, ValueError, KeyError):
                return None
        return None

    def _cache_put(self, key: str, content: str) -> None:
        path = self._cache_path(key)
        path.parent.mkdir(parents=True, exist_ok=True)
        with contextlib.suppress(OSError):
            # A cache miss is not worth failing the run over.
            path.write_text(
                json.dumps({"key": key, "content": content}),
                encoding="utf-8",
                newline="\n",
            )

    # -- budget ----------------------------------------------------------- #
    def budget(self) -> dict[str, Any]:
        """Remaining free-tier allowance, or ``{}`` when the provider has no
        budget endpoint or no key is configured."""
        endpoint = BUDGET_ENDPOINTS.get(self.provider)
        if not endpoint or not self.api_key:
            return {}
        try:
            r = requests.get(
                endpoint,
                headers={"Authorization": f"Bearer {self.api_key}"},
                timeout=20,
            )
            r.raise_for_status()
            data = r.json().get("data", {})
            remaining = data.get("free_model_daily_requests")
            if remaining is None:
                return {}
            return remaining
        except Exception:
            return {}

    # -- headers ---------------------------------------------------------- #
    def _headers(self) -> dict[str, str]:
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }
        if self.provider == "openrouter":
            # OpenRouter uses these for dashboard attribution.
            headers["HTTP-Referer"] = "https://github.com/apksmith"
            headers["X-Title"] = "APKSmith"
        return headers

    # -- completion ------------------------------------------------------- #
    def complete(
        self,
        system: str,
        user: str,
        *,
        json_mode: bool = True,
        max_tokens: int = 4096,
        temperature: float = 0.1,
    ) -> str:
        """Send one chat completion and return the assistant's text.

        Retries on 429 and on 5xx with exponential backoff, because a free
        tier hitting a transient limit is the normal case, not an exception.
        """
        if not self.api_key:
            env_name = {
                "openrouter": "OPENROUTER_API_KEY",
                "groq": "GROQ_API_KEY",
            }[self.provider]
            raise LlmUnavailable(
                f"No API key for {self.provider}. Set {env_name}, or pass one "
                f"explicitly. Free keys: "
                + (
                    "https://openrouter.ai/keys"
                    if self.provider == "openrouter"
                    else "https://console.groq.com/keys"
                )
            )

        cache_key = json.dumps(
            {
                "provider": self.provider,
                "model": self.model,
                "system": system,
                "user": user,
                "temperature": temperature,
                "max_tokens": max_tokens,
            },
            sort_keys=True,
        )

        cached = self._cache_get(cache_key)
        if cached is not None:
            self.stats.cached += 1
            return cached

        payload: dict[str, Any] = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            "temperature": temperature,
            "max_tokens": max_tokens,
        }
        if json_mode:
            # Small models drift badly without this. Groq additionally
            # supports json_schema, which is stricter, but json_object is
            # portable across both providers and our parser handles the rest.
            payload["response_format"] = {"type": "json_object"}

        url = ENDPOINTS[self.provider]
        last_error = "no attempt made"

        for attempt in range(self.max_retries):
            try:
                resp = requests.post(
                    url,
                    headers=self._headers(),
                    json=payload,
                    timeout=self.timeout,
                )
            except requests.RequestException as exc:
                last_error = f"could not reach {self.provider}: {exc}"
                self._sleep(attempt)
                self.stats.retries += 1
                continue

            if resp.status_code == 429:
                # Respect Retry-After when the provider sends one.
                wait = float(resp.headers.get("retry-after") or 0) or 0.0
                if not wait:
                    wait = 2.0 * (2**attempt)
                self.stats.retries += 1
                last_error = (
                    f"rate limited by {self.provider}. {FREE_TIER_HELP[self.provider]}"
                )
                if attempt < self.max_retries - 1:
                    self._sleep(attempt, forced=wait)
                    continue
                self.stats.failures += 1
                raise LlmUnavailable(last_error)

            if resp.status_code >= 500:
                self.stats.retries += 1
                last_error = f"{self.provider} returned {resp.status_code}"
                if attempt < self.max_retries - 1:
                    self._sleep(attempt)
                    continue
                self.stats.failures += 1
                raise LlmUnavailable(last_error)

            if resp.status_code >= 400:
                self.stats.failures += 1
                raise LlmUnavailable(
                    f"{self.provider} returned {resp.status_code}: {resp.text[:400]}"
                )

            data = resp.json()
            usage = data.get("usage") or {}
            self.stats.requests += 1
            self.stats.prompt_tokens += int(usage.get("prompt_tokens") or 0)
            self.stats.completion_tokens += int(usage.get("completion_tokens") or 0)

            try:
                content = data["choices"][0]["message"]["content"]
            except (KeyError, IndexError, TypeError) as exc:
                last_error = f"malformed response from {self.provider}: {exc}"
                self.stats.retries += 1
                if attempt < self.max_retries - 1:
                    self._sleep(attempt)
                    continue
                self.stats.failures += 1
                raise LlmUnavailable(last_error) from exc

            self._cache_put(cache_key, content)
            return content

        self.stats.failures += 1
        raise LlmUnavailable(last_error)

    @staticmethod
    def _sleep(attempt: int, forced: float | None = None) -> None:
        import time

        delay = forced if forced else 1.5 * (2**attempt)
        time.sleep(min(delay, 30.0))


# --------------------------------------------------------------------------- #
# JSON extraction
# --------------------------------------------------------------------------- #
def parse_json_loose(text: str) -> dict[str, Any] | None:
    """Pull a JSON object out of a model response.

    Models wrap JSON in prose, fence it in markdown, or emit trailing commas.
    Rather than trusting tidy output, peel it off in stages: direct parse,
    then a fenced block, then the outermost brace span, then trailing-comma
    repair.
    """
    if not text:
        return None

    try:
        value = json.loads(text)
        return value if isinstance(value, dict) else None
    except json.JSONDecodeError:
        pass

    fence = text.find("```")
    if fence != -1:
        rest = text[fence + 3 :]
        if rest[:4].lower() == "json":
            rest = rest[4:]
        end = rest.find("```")
        if end != -1:
            rest = rest[:end]
        try:
            value = json.loads(rest.strip())
            return value if isinstance(value, dict) else None
        except json.JSONDecodeError:
            pass

    start, end = text.find("{"), text.rfind("}")
    if start != -1 and end > start:
        candidate = text[start : end + 1]
        try:
            value = json.loads(candidate)
            return value if isinstance(value, dict) else None
        except json.JSONDecodeError:
            pass
        # Last resort: strip trailing commas before } or ].
        repaired = re.sub(r",\s*([}\]])", r"\1", candidate)
        try:
            value = json.loads(repaired)
            return value if isinstance(value, dict) else None
        except json.JSONDecodeError:
            pass

    return None
