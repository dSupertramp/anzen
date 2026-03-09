"""OpenAI integration"""

from anzen.client import wrap as _wrap
from anzen.config import AnzenConfig
from anzen.integrations._base import BaseAdapter, BaseCompletions


class OpenAICompletions(BaseCompletions):
    """Pass-through adapter: OpenAI client already exposes chat.completions."""

    def create(self, messages=None, **kwargs):
        return self._client.chat.completions.create(messages=messages, **kwargs)

    async def acreate(self, messages=None, **kwargs):
        comp = self._client.chat.completions
        if hasattr(comp, "acreate"):
            return await comp.acreate(messages=messages, **kwargs)
        # AsyncOpenAI uses create() for async
        coro = comp.create(messages=messages, **kwargs)
        if hasattr(coro, "__await__"):
            return await coro
        raise NotImplementedError("OpenAI sync client does not support async; use AsyncOpenAI")


def wrap_openai(client, config: AnzenConfig | None, session_id: str | None):
    """Wrap an OpenAI client with Anzen. Returns an Anzen-wrapped OpenAI client."""
    return _wrap(BaseAdapter(OpenAICompletions(client)), config=config, session_id=session_id)
