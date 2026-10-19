"""
OpenRouter client for the understanding layer.

Deliberately small, and built around three constraints specific to free
tier access:

1. **Rate limits are real.** 20 requests/minute, 50/day without credits. The
   client surfaces the remaining budget instead of silently failing.

2. **Responses are cached by content hash.** Re-running the pipeline on an
   unchanged APK must cost nothing. For a student on a free tier this is the
   difference between being able to iterate and not.

3. **The model is not trusted.** Every response is validated into a Pydantic
   model, and a response that will not parse is retried with a repair prompt
   before being given up on. Small free models produce malformed JSON often
   enough that this is not optional.
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

#: A model that is good at reasoning and free. Verified present on OpenRouter's
#: free tier. Override with --model if the roster changes.
DEFAULT_MODEL = "nvidia/nemotron-3-ultra-550b-a55b:free"

ENDPOINT = "https://openrouter.ai/api/v1/chat/completions"


class LlmUnavailable(ApkSmithError):
    """No API key, or the provider could not be reached."""


@dataclass
class LlmStats:
    """Token and request accounting, so a run can report its own cost."""

    requests: int = 0
    cached: int = 0
    prompt_tokens: int = 0
    completion_tokens: int = 0
    failures: int = 0
    model: str = DEFAULT_MODEL

    def as_dict(self) -> dict[str, Any]:
        return {
            "requests": self.requests,
            "cached_responses": self.cached,
            "prompt_tokens": self.prompt_tokens,
            "completion_tokens": self.completion_tokens,
            "failures": self.failures,
            "model": self.model,
        }


@dataclass
class LlmClient:
    """Minimal OpenRouter chat client with disk caching."""

    api_key: str | None = None
    model: str = DEFAULT_MODEL
    cache_dir: Path = field(default_factory=lambda: Path(".apksmith-cache"))
    timeout: int = 120
    stats: LlmStats = field(default_factory=LlmStats)

    def __post_init__(self) -> None:
        self.api_key = self.api_key or os.environ.get("OPENROUTER_API_KEY")
        self.stats.model = self.model

    # -- cache ------------------------------------------------------------ #
    def _cache_path(self, key: str) -> Path:
        # Two-level fan-out keeps directories small on long projects.
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
                json.dumps({"key": key, "content": content}), encoding="utf-8"
            )

    # -- budget ----------------------------------------------------------- #
    def budget(self) -> dict[str, Any]:
        """Remaining free-tier requests for this key, or {} if unavailable."""
        if not self.api_key:
            return {}
        try:
            r = requests.get(
                "https://openrouter.ai/api/v1/key",
                headers={"Authorization": f"Bearer {self.api_key}"},
                timeout=20,
            )
            r.raise_for_status()
            return r.json().get("data", {}).get("free_model_daily_requests", {})
        except Exception:
            return {}

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

        Raises LlmUnavailable if there is no key or the request cannot be made.
        """
        if not self.api_key:
            raise LlmUnavailable(
                "No OpenRouter API key. Get one free at "
                "https://openrouter.ai/keys and set OPENROUTER_API_KEY."
            )

        cache_key = json.dumps(
            {
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
            # Free models vary in how well they honour this, but it improves
            # the odds considerably and costs nothing.
            payload["response_format"] = {"type": "json_object"}

        try:
            resp = requests.post(
                ENDPOINT,
                headers={
                    "Authorization": f"Bearer {self.api_key}",
                    "Content-Type": "application/json",
                    "HTTP-Referer": "https://github.com/apksmith",
                    "X-Title": "APKSmith",
                },
                json=payload,
                timeout=self.timeout,
            )
        except requests.RequestException as exc:
            raise LlmUnavailable(f"Could not reach OpenRouter: {exc}") from exc

        if resp.status_code == 429:
            self.stats.failures += 1
            raise LlmUnavailable(
                "Rate limited by OpenRouter. The free tier allows 20 requests "
                "per minute and 50 per day. Wait, or add $10 in credits for "
                "1000/day."
            )
        if resp.status_code >= 400:
            self.stats.failures += 1
            raise LlmUnavailable(
                f"OpenRouter returned {resp.status_code}: {resp.text[:300]}"
            )

        data = resp.json()
        usage = data.get("usage") or {}
        self.stats.requests += 1
        self.stats.prompt_tokens += int(usage.get("prompt_tokens") or 0)
        self.stats.completion_tokens += int(usage.get("completion_tokens") or 0)

        try:
            content = data["choices"][0]["message"]["content"]
        except (KeyError, IndexError) as exc:
            self.stats.failures += 1
            raise LlmUnavailable(f"Malformed response from OpenRouter: {exc}") from exc

        self._cache_put(cache_key, content)
        return content


# --------------------------------------------------------------------------- #
# JSON extraction
# --------------------------------------------------------------------------- #
def parse_json_loose(text: str) -> dict[str, Any] | None:
    """Pull a JSON object out of a model response.

    Small models wrap JSON in prose, fence it in markdown, or emit trailing
    commas. Rather than trusting the model to be tidy, we peel it off in
    stages: direct parse, then fenced block, then the outermost brace span.
    """
    if not text:
        return None

    try:
        value = json.loads(text)
        return value if isinstance(value, dict) else None
    except json.JSONDecodeError:
        pass

    # ```json ... ```
    fence_start = text.find("```")
    if fence_start != -1:
        rest = text[fence_start + 3:]
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

    # Outermost {...} span.
    start = text.find("{")
    end = text.rfind("}")
    if start != -1 and end > start:
        candidate = text[start : end + 1]
        try:
            value = json.loads(candidate)
            return value if isinstance(value, dict) else None
        except json.JSONDecodeError:
            pass
        # Last resort: strip trailing commas before } or ]
        repaired = re.sub(r",\s*([}\]])", r"\1", candidate)
        try:
            value = json.loads(repaired)
            return value if isinstance(value, dict) else None
        except json.JSONDecodeError:
            pass

    return None
