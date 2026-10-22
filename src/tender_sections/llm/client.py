"""The LLM behind stage 7: a protocol, the Anthropic implementation, and a scripted fake for tests."""

from __future__ import annotations

import json
import os
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any, Protocol

from tender_sections.config import Effort, LLMSettings

_FALLBACK_BETA = "server-side-fallback-2026-07-01"


class LLMError(RuntimeError):
    """No usable answer: an API error after the SDK's retries, a refusal, or a cut-off reply."""


class LLMNotConfigured(LLMError):
    """The LLM is on but cannot be called: no API key. Raised when the client is built."""


@dataclass
class LLMReply:
    data: Any  # the JSON answer, parsed; None when the text is not JSON
    text: str  # the answer as the model wrote it
    input_tokens: int = 0
    output_tokens: int = 0


class LLMClient(Protocol):
    def complete_json(
        self, *, system: str, user: str, schema: dict[str, Any], max_tokens: int, effort: Effort
    ) -> LLMReply: ...


class AnthropicClient:
    """Claude through the Anthropic SDK, its answer constrained to a JSON schema.

    The schema goes in output_config.format (structured outputs): Claude Sonnet 5.5 rejects forced
    tool use. A refusal is retried server-side on the recommended fallback model
    (fallbacks="default"); if the whole chain refuses, the caller gets an LLMError.
    """

    def __init__(self, settings: LLMSettings) -> None:
        import anthropic
        from dotenv import load_dotenv

        load_dotenv()  # ANTHROPIC_API_KEY and LLM_MODEL from .env; the environment wins
        self.model = settings.model or os.environ.get("LLM_MODEL") or settings.default_model
        self._settings = settings
        self._api_error = anthropic.APIError
        self._client = anthropic.Anthropic(timeout=settings.timeout_seconds)
        if not (self._client.api_key or getattr(self._client, "auth_token", None)):
            # Otherwise the SDK fails only at the first request, with a TypeError.
            raise LLMNotConfigured(
                "ANTHROPIC_API_KEY is not set: add it to .env, or turn the LLM off "
                "(--no-llm, or llm.enabled: false)"
            )

    def complete_json(
        self, *, system: str, user: str, schema: dict[str, Any], max_tokens: int, effort: Effort
    ) -> LLMReply:
        request: dict[str, Any] = {
            "model": self.model,
            "max_tokens": max_tokens,
            "system": system,
            "messages": [{"role": "user", "content": user}],
            "output_config": {
                "effort": effort,
                "format": {"type": "json_schema", "schema": schema},
            },
        }
        try:
            if self._settings.fallbacks:
                response = self._client.beta.messages.create(
                    betas=[_FALLBACK_BETA], fallbacks=self._settings.fallbacks, **request
                )
            else:
                response = self._client.messages.create(**request)
        except self._api_error as error:  # the SDK has already retried 429, 5xx and timeouts
            raise LLMError(f"{type(error).__name__}: {error}") from error
        if response.stop_reason == "refusal":
            category = getattr(response.stop_details, "category", None)
            raise LLMError(f"the model declined the request (category {category})")
        if response.stop_reason == "max_tokens":
            raise LLMError(f"the answer was cut off at max_tokens={max_tokens}")
        # Read by block type: with adaptive thinking the answer can follow a thinking block.
        text = "".join(block.text for block in response.content if block.type == "text")
        return LLMReply(
            data=_json_or_none(text),
            text=text,
            input_tokens=response.usage.input_tokens,
            output_tokens=response.usage.output_tokens,
        )


@dataclass
class FakeLLMClient:
    """A scripted stand-in for tests, which may never reach the network (CLAUDE.md hard rule 16).

    `answer` gets each request (system, user, schema, max_tokens, effort) and returns the JSON
    answer, or raises LLMError. Every request is kept in `requests`.
    """

    answer: Callable[[dict[str, Any]], Any]
    model: str = "fake"
    requests: list[dict[str, Any]] = field(default_factory=list)

    def complete_json(
        self, *, system: str, user: str, schema: dict[str, Any], max_tokens: int, effort: Effort
    ) -> LLMReply:
        request = {
            "system": system,
            "user": user,
            "schema": schema,
            "max_tokens": max_tokens,
            "effort": effort,
        }
        self.requests.append(request)
        answer = self.answer(request)
        text = answer if isinstance(answer, str) else json.dumps(answer)
        return LLMReply(
            data=_json_or_none(text),
            text=text,
            input_tokens=len(system + user) // 4,
            output_tokens=len(text) // 4,
        )


def _json_or_none(text: str) -> Any:
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        return None
