import requests
import httpx
from typing import Any
from anzen.client import wrap as _wrap
from anzen.config import AnzenConfig
from anzen.integrations._base import BaseAdapter, BaseCompletions, messages_to_prompt


class OllamaCompletions(BaseCompletions):
    def _sync_post(self, url, json):
        if requests is None:
            raise RuntimeError("requests required for Ollama; pip install requests")
        r = requests.post(url, json=json)
        r.raise_for_status()
        return r.json()

    def create(self, messages=None, **kwargs):
        prompt = messages_to_prompt(messages) if messages else kwargs.pop("prompt", "")
        model = kwargs.pop("model", None)
        if isinstance(self._client, str):
            base = self._client.rstrip("/")
            msg = [{"role": "user", "content": prompt}]
            for endpoint, payload in [
                ("/v1/chat/completions", {"model": model, "messages": msg, "stream": False}),
                ("/api/chat", {"model": model, "messages": msg, "stream": False}),
                ("/api/generate", {"model": model, "prompt": prompt, "stream": False}),
            ]:
                try:
                    r = self._sync_post(base + endpoint, payload)
                    if endpoint == "/v1/chat/completions":
                        return r
                    if endpoint == "/api/chat":
                        content = r.get("message", {}).get("content", "") or ""
                        return {
                            "choices": [{"message": {"role": "assistant", "content": content}}],
                            "response": content,
                            **r,
                        }
                    # /api/generate
                    content = r.get("response", "") or ""
                    return {
                        "choices": [{"message": {"role": "assistant", "content": content}}],
                        **r,
                    }
                except Exception:
                    continue
            raise RuntimeError("Ollama: all endpoints failed (ollama serve?)")
        if hasattr(self._client, "chat"):
            r = self._client.chat(model=model, messages=[{"role": "user", "content": prompt}])
            content = r.get("message", {}).get("content", "") or ""
            return {
                "choices": [{"message": {"role": "assistant", "content": content}}],
                "response": content,
                **r,
            }
        if hasattr(self._client, "generate"):
            r = self._client.generate(prompt=prompt, model=model, **kwargs)
            if isinstance(r, dict):
                content = r.get("response", "") or ""
                return {
                    "choices": [{"message": {"role": "assistant", "content": content}}],
                    **r,
                }
            return r
        raise NotImplementedError("Ollama: pass URL or ollama client")

    async def acreate(self, messages=None, **kwargs):
        prompt = messages_to_prompt(messages) if messages else kwargs.pop("prompt", "")
        model = kwargs.pop("model", None)
        if isinstance(self._client, str):
            if httpx is None:
                raise RuntimeError("httpx required for Ollama async; pip install httpx")
            base = self._client.rstrip("/")
            msg = [{"role": "user", "content": prompt}]
            for endpoint, payload in [
                ("/v1/chat/completions", {"model": model, "messages": msg, "stream": False}),
                ("/api/chat", {"model": model, "messages": msg, "stream": False}),
                ("/api/generate", {"model": model, "prompt": prompt, "stream": False}),
            ]:
                try:
                    async with httpx.AsyncClient() as c:
                        r = await c.post(base + endpoint, json=payload)
                        r.raise_for_status()
                        data = r.json()
                    if endpoint == "/v1/chat/completions":
                        return data
                    if endpoint == "/api/chat":
                        content = data.get("message", {}).get("content", "") or ""
                        return {
                            "choices": [{"message": {"role": "assistant", "content": content}}],
                            "response": content,
                            **data,
                        }
                    # /api/generate
                    content = data.get("response", "") or ""
                    return {
                        "choices": [{"message": {"role": "assistant", "content": content}}],
                        **data,
                    }
                except Exception:
                    continue
            raise RuntimeError("Ollama: all endpoints failed (ollama serve?)")
        raise NotImplementedError("Ollama async: pass URL string")


def wrap_ollama(client_or_url: Any, config: AnzenConfig | None, session_id: str | None):
    """Wrap Ollama (URL or `ollama` client) with Anzen. Returns an Anzen-wrapped client."""
    return _wrap(BaseAdapter(OllamaCompletions(client_or_url)), config=config, session_id=session_id)
