from anzen.client import wrap as _wrap
from anzen.config import AnzenConfig
from anzen.integrations._base import BaseAdapter, BaseCompletions, messages_to_prompt


class CohereCompletions(BaseCompletions):
    def create(self, messages=None, **kwargs):
        model = kwargs.pop("model", "command-r-plus")
        # SDK v5 (ClientV2): accepts messages list directly
        if hasattr(self._client, "chat") and _is_v2(self._client):
            msgs = messages or []
            r = self._client.chat(model=model, messages=msgs, **kwargs)
            return _normalize_cohere(r)
        # SDK v4 (Client): expects a plain message string + optional chat_history
        prompt = messages_to_prompt(messages) if messages else kwargs.pop("message", "")
        r = self._client.chat(model=model, message=prompt, **kwargs)
        return _normalize_cohere(r)

    async def acreate(self, messages=None, **kwargs):
        model = kwargs.pop("model", "command-r-plus")
        if hasattr(self._client, "chat") and _is_v2(self._client):
            msgs = messages or []
            r = await self._client.chat(model=model, messages=msgs, **kwargs)
            return _normalize_cohere(r)
        raise NotImplementedError("Cohere v4 async: use cohere.AsyncClient")


def _is_v2(client) -> bool:
    """Detect SDK v5 ClientV2 by presence of a versioned attribute."""
    return type(client).__name__ in ("ClientV2", "AsyncClientV2")


def _normalize_cohere(r) -> dict:
    """Normalize Cohere response to OpenAI-style choices dict."""
    # SDK v5: r.message.content[0].text
    if hasattr(r, "message") and hasattr(r.message, "content"):
        content = r.message.content
        text = content[0].text if content and hasattr(content[0], "text") else str(content)
        return {"choices": [{"message": {"role": "assistant", "content": text}}]}
    # SDK v4: r.text
    if hasattr(r, "text"):
        return {"choices": [{"message": {"role": "assistant", "content": r.text}}]}
    return {"choices": [{"message": {"role": "assistant", "content": str(r)}}]}


def wrap_cohere(client, config: AnzenConfig | None = None, session_id: str | None = None):
    """Wrap a Cohere client with Anzen. Returns an Anzen-wrapped client."""
    return _wrap(BaseAdapter(CohereCompletions(client)), config=config, session_id=session_id)
