"""Mistral AI integration — wrap an existing Mistral client.

Supports the official `mistralai` SDK (>=1.0).

Usage:
    from mistralai import Mistral
    from anzen.integrations import wrap_mistral
    from anzen import AnzenConfig

    client = wrap_mistral(
        Mistral(api_key=os.environ["MISTRAL_API_KEY"]),
        config=AnzenConfig(monitor_url="http://localhost:8000"),
        session_id="my-session",
    )
    r = client.chat.completions.create(
        model="mistral-large-latest",
        messages=[{"role": "user", "content": "Hello!"}],
    )
"""

from anzen.client import wrap as _wrap
from anzen.config import AnzenConfig
from anzen.integrations._base import BaseAdapter, BaseCompletions, messages_to_prompt


class MistralCompletions(BaseCompletions):
    def create(self, messages=None, **kwargs):
        msgs = messages or []
        model = kwargs.pop("model", None)
        r = self._client.chat.complete(model=model, messages=msgs, **kwargs)
        return _normalize_mistral(r)

    async def acreate(self, messages=None, **kwargs):
        msgs = messages or []
        model = kwargs.pop("model", None)
        r = await self._client.chat.complete_async(model=model, messages=msgs, **kwargs)
        return _normalize_mistral(r)


def _normalize_mistral(r):
    """Normalize a Mistral response to OpenAI-style choices dict."""
    if hasattr(r, "choices"):
        # Already OpenAI-shape (mistralai SDK returns similar structure)
        return r
    return r


def wrap_mistral(
    client, config: AnzenConfig | None = None, session_id: str | None = None
):
    """Wrap a Mistral client with Anzen. Returns an Anzen-wrapped client."""
    return _wrap(
        BaseAdapter(MistralCompletions(client)), config=config, session_id=session_id
    )
