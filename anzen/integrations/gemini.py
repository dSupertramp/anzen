from anzen.client import wrap as _wrap
from anzen.config import AnzenConfig
from anzen.integrations._base import BaseAdapter, BaseCompletions, messages_to_prompt


class GeminiCompletions(BaseCompletions):
    def create(self, messages=None, **kwargs):
        prompt = messages_to_prompt(messages) if messages else kwargs.pop("contents", "")
        model = kwargs.pop("model", None)
        if hasattr(self._client, "models") and hasattr(self._client.models, "generate_content"):
            return self._client.models.generate_content(model=model, contents=prompt, **kwargs)
        if hasattr(self._client, "generate"):
            return self._client.generate(prompt)
        raise NotImplementedError("Gemini client needs models.generate_content or generate")

    async def acreate(self, messages=None, **kwargs):
        prompt = messages_to_prompt(messages) if messages else kwargs.pop("contents", "")
        model = kwargs.pop("model", None)
        if hasattr(self._client, "models") and hasattr(self._client.models, "agenerate_content"):
            return await self._client.models.agenerate_content(model=model, contents=prompt, **kwargs)
        raise NotImplementedError("Gemini client has no async generate_content")


def wrap_gemini(client, config: AnzenConfig | None, session_id: str | None):
    """Wrap a Gemini client with Anzen. Returns an Anzen-wrapped client."""
    return _wrap(BaseAdapter(GeminiCompletions(client)), config=config, session_id=session_id)
