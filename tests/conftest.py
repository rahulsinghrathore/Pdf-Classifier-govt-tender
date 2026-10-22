"""No test may reach the network (CLAUDE.md hard rule 16).

extract() builds the Anthropic client by default, and .env holds a real key. In tests the LLM is
off unless a test hands extract() a FakeLLMClient, and building the real client fails loudly.
"""

from __future__ import annotations

import pytest

from tender_sections.llm.client import AnthropicClient

# For a test that checks the constructor itself against a stubbed SDK (test_cli.py).
REAL_ANTHROPIC_INIT = AnthropicClient.__init__


@pytest.fixture(autouse=True)
def _no_network_llm(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("TENDER_LLM__ENABLED", "false")

    def refuse(*args: object, **kwargs: object) -> None:
        raise AssertionError("a test tried to build the real Anthropic client; use FakeLLMClient")

    monkeypatch.setattr(AnthropicClient, "__init__", refuse)
