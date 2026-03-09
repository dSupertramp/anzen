"""Azure OpenAI integration"""

from anzen.client import wrap as _wrap
from anzen.config import AnzenConfig
from anzen.integrations._base import BaseAdapter, BaseCompletions


class AzureOpenAICompletions(BaseCompletions):
    """Pass-through adapter: AzureOpenAI client is OpenAI-compatible."""

    def create(self, messages=None, **kwargs):
        return self._client.chat.completions.create(messages=messages, **kwargs)

    async def acreate(self, messages=None, **kwargs):
        comp = self._client.chat.completions
        if hasattr(comp, "acreate"):
            return await comp.acreate(messages=messages, **kwargs)
        # AsyncAzureOpenAI uses create() as a coroutine
        coro = comp.create(messages=messages, **kwargs)
        if hasattr(coro, "__await__"):
            return await coro
        raise NotImplementedError("AzureOpenAI sync client does not support async; use AsyncAzureOpenAI")


def wrap_azure_openai(client, config: AnzenConfig | None = None, session_id: str | None = None):
    """Wrap an AzureOpenAI client with Anzen. Returns an Anzen-wrapped client."""
    return _wrap(
        BaseAdapter(AzureOpenAICompletions(client)),
        config=config,
        session_id=session_id,
    )
