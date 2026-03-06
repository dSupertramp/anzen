from abc import ABC, abstractmethod


class BaseCompletions(ABC):
    """
    Subclass this for each provider. Implement create() and optionally acreate().
    The adapter must accept (messages=None, **kwargs) and return a response
    compatible with extract_text().
    """

    def __init__(self, client):
        self._client = client

    @abstractmethod
    def create(self, messages=None, **kwargs):
        """Sync completion. Must accept OpenAI-style messages or provider-specific kwargs."""
        ...

    async def acreate(self, messages=None, **kwargs):
        """Async completion. Override in subclasses that support async."""
        raise NotImplementedError(f"{self.__class__.__name__} does not support async")


class BaseAdapter:
    """
    Universal adapter that exposes a client.chat.completions interface.
    Pass a BaseCompletions instance to produce an Anzen-compatible client.
    """

    def __init__(self, completions: BaseCompletions):
        self.chat = type("_Chat", (), {"completions": completions})()


def messages_to_prompt(messages: list[dict[str, str]]) -> str:
    """Convert an OpenAI-style `messages` list to a plain prompt string.

    Keeps only `content` fields and preserves ordering. This is a
    best-effort converter used when adapting non-OpenAI clients.
    """
    if not messages:
        return ""
    parts = []
    for m in messages:
        if isinstance(m, dict):
            content = m.get("content") or m.get("text")
            if content:
                parts.append(str(content))
        else:
            parts.append(str(m))
    return "\n\n".join(parts)


def ensure_list(v):
    if v is None:
        return []
    if isinstance(v, list):
        return v
    return [v]


def extract_text(r) -> str:
    """Extract response text from various provider formats (incl. Anzen mock)."""
    if isinstance(r, dict):
        c = (r.get("choices") or [{}])[0].get("message", {}).get("content")
        if c:
            return c
        c = r.get("message", {}).get("content") if isinstance(r.get("message"), dict) else None
        if c:
            return c
        return r.get("response", r.get("text", ""))
    if hasattr(r, "choices"):
        return r.choices[0].message.content
    if hasattr(r, "content") and getattr(r, "content", None):
        blocks = r.content if isinstance(r.content, (list, tuple)) else [r.content]
        if blocks and hasattr(blocks[0], "text"):
            return blocks[0].text
    if hasattr(r, "text"):
        return r.text
    return str(r) if r else ""
