"""
Anzen — Open-source security layer for agentic AI.

Protects against:
  - Prompt injection (user messages)
  - RAG poisoning (document chunks)
  - Tool abuse (tool calls & parameters)
  - Anomalous session behavior

Usage:
    import anzen

    # Wrap any OpenAI-compatible client
    client = anzen.wrap(openai.OpenAI())

    # Or use guards individually
    from anzen import RAGGuard, ToolGuard, PromptGuard
"""

from anzen.client import Anzen, wrap
from anzen.config import AnzenConfig
from anzen.events import EventBus, GuardEvent, EventAction, GuardType
from anzen.exceptions import (
    BlockedError,
    AnzenError,
    PromptBlockedError,
    RAGBlockedError,
    ToolBlockedError,
)
from anzen.guards.prompt import PromptGuard
from anzen.guards.rag import RAGGuard, ChunkResult
from anzen.guards.tool import ToolGuard, ToolCallResult

__all__ = [
    "Anzen",
    "wrap",
    "BlockedError",
    "AnzenError",
    "PromptBlockedError",
    "RAGBlockedError",
    "ToolBlockedError",
    "PromptGuard",
    "RAGGuard",
    "ChunkResult",
    "ToolGuard",
    "ToolCallResult",
    "AnzenConfig",
    "EventBus",
    "GuardEvent",
    "EventAction",
    "GuardType",
]

__version__ = "0.1.0"
