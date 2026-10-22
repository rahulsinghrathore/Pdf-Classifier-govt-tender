"""Stage 7 and the whole-document fallback: the only places the LLM is used (SPEC §7, §9).

Nothing in the deterministic stages imports this package (CLAUDE.md hard rule 3).
"""

from tender_sections.llm.adjudicate import Adjudication, adjudicate
from tender_sections.llm.client import (
    AnthropicClient,
    FakeLLMClient,
    LLMClient,
    LLMError,
    LLMNotConfigured,
    LLMReply,
)
from tender_sections.llm.whole_doc import WholeDocument, whole_document_pass

__all__ = [
    "Adjudication",
    "AnthropicClient",
    "FakeLLMClient",
    "LLMClient",
    "LLMError",
    "LLMNotConfigured",
    "LLMReply",
    "WholeDocument",
    "adjudicate",
    "whole_document_pass",
]
