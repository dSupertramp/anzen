"""Anthropic integration"""

from anzen.client import wrap as _wrap
from anzen.config import AnzenConfig
from anzen.integrations._base import BaseAdapter, BaseCompletions, messages_to_prompt


class AnthropicCompletions(BaseCompletions):
    def create(self, messages=None, **kwargs):
        prompt = messages_to_prompt(messages) if messages else kwargs.pop("prompt", "")
        model = kwargs.pop("model", None)
        return self._client.messages.create(
            model=model,
            max_tokens=kwargs.pop("max_tokens", 1024),
            messages=[{"role": "user", "content": prompt}],
            **kwargs,
        )

    async def acreate(self, messages=None, **kwargs):
        prompt = messages_to_prompt(messages) if messages else kwargs.pop("prompt", "")
        model = kwargs.pop("model", None)
        return await self._client.messages.create(
            model=model,
            max_tokens=kwargs.pop("max_tokens", 1024),
            messages=[{"role": "user", "content": prompt}],
            **kwargs,
        )


def wrap_anthropic(client, config: AnzenConfig | None = None, session_id: str | None = None):
    """Wrap an Anthropic client with Anzen. Returns an Anzen-wrapped client."""
    return _wrap(BaseAdapter(AnthropicCompletions(client)), config=config, session_id=session_id)
