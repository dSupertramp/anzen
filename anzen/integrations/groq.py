"""Groq integration — wrap an existing Groq client.

Groq exposes an OpenAI-compatible API, so create() passes through directly.
"""

from anzen.client import wrap as _wrap
from anzen.config import AnzenConfig
from anzen.integrations._base import BaseAdapter, BaseCompletions


class GroqCompletions(BaseCompletions):
    """Pass-through adapter: Groq client is OpenAI-compatible."""

    def create(self, messages=None, **kwargs):
        return self._client.chat.completions.create(messages=messages, **kwargs)

    async def acreate(self, messages=None, **kwargs):
        # groq.AsyncGroq uses create() as a coroutine
        coro = self._client.chat.completions.create(messages=messages, **kwargs)
        if hasattr(coro, "__await__"):
            return await coro
        raise NotImplementedError("Groq sync client does not support async; use AsyncGroq")


def wrap_groq(client, config: AnzenConfig | None = None, session_id: str | None = None):
    """Wrap a Groq client with Anzen. Returns an Anzen-wrapped client."""
    return _wrap(BaseAdapter(GroqCompletions(client)), config=config, session_id=session_id)
