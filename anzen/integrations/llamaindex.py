"""
Anzen LlamaIndex integration.

Usage:
    from llama_index.core import Settings
    from anzen.integrations.llamaindex import AnzenObserver
    from anzen import AnzenConfig

    observer = AnzenObserver(
        config=AnzenConfig(monitor_url="http://localhost:3000"),
    )
    Settings.callback_manager.add_handler(observer)

    # RAG pipeline
    safe_nodes = observer.filter_nodes(nodes, query_str=query)
"""

from typing import Any, Dict, List

try:
    from llama_index.core.callbacks.schema import CBEventType
except ImportError:
    CBEventType = None

from anzen.client import Anzen
from anzen.exceptions import PromptBlockedError, ToolBlockedError
from anzen.config import AnzenConfig


class AnzenObserver:
    """
    LlamaIndex callback handler compatible with CallbackManager.
    Works with QueryEngine, RetrieverQueryEngine, and agent workflows.
    """

    event_starts_to_ignore: List = []
    event_ends_to_ignore: List = []

    def __init__(
        self,
        config: AnzenConfig | None = None,
        block_on_injection: bool = True,
        monitor_tools: bool = True,
        monitor_rag: bool = True,
        session_id: str | None = None,
    ):
        self.block_on_injection = block_on_injection
        self.monitor_tools = monitor_tools
        self.monitor_rag = monitor_rag

        cfg = config or AnzenConfig()

        self._agent = Anzen(client=_NoOpClient(), config=cfg, session_id=session_id)

    # ─── LlamaIndex CBEventType hooks ────────────────────────────────────────

    def on_event_start(
        self,
        event_type,
        payload: Dict[str, Any] | None = None,
        event_id: str = "",
        **kwargs,
    ) -> str:
        if payload is None or CBEventType is None:
            return event_id

        if event_type == CBEventType.LLM:
            messages = payload.get("messages", [])
            for msg in messages:
                content = getattr(msg, "content", None) or (
                    msg.get("content") if isinstance(msg, dict) else None
                )
                if content:
                    safe = self._agent.check_prompt(str(content))
                    if not safe and self.block_on_injection:
                        raise PromptBlockedError(self._agent.config.block_message)

        elif event_type == CBEventType.FUNCTION_CALL and self.monitor_tools:
            tool_name = payload.get("tool", {})
            if hasattr(tool_name, "name"):
                tool_name = tool_name.name
            params = payload.get("tool_kwargs", {})
            safe = self._agent.check_tool(str(tool_name), params)
            if not safe and self.block_on_injection:
                raise ToolBlockedError(
                    self._agent.config.block_message,
                    tool_name=str(tool_name),
                )

        return event_id

    def on_event_end(
        self,
        event_type,
        payload: Dict[str, Any] | None = None,
        event_id: str = "",
        **kwargs,
    ) -> None:
        pass

    def start_trace(self, trace_id: str | None = None) -> None:
        pass

    def end_trace(
        self,
        trace_id: str | None = None,
        trace_map: Dict[str, List[str]] | None = None,
    ) -> None:
        pass

    # ─── RAG helper ──────────────────────────────────────────────────────────

    def filter_nodes(self, nodes: List, query_str: str | None = None) -> List:
        """
        Filter LlamaIndex NodeWithScore or TextNode objects through RAGGuard.

        Example:
            nodes = retriever.retrieve(query)
            safe_nodes = observer.filter_nodes(nodes, query_str=query)
        """
        if not self.monitor_rag:
            return nodes

        # Convert nodes to text for scanning, preserve originals
        def extract(node) -> str:
            if hasattr(node, "node"):
                return getattr(node.node, "text", str(node))
            return getattr(node, "text", str(node))

        texts = [extract(n) for n in nodes]
        result = self._agent.rag_guard.scan(texts, query=query_str)

        # Return only nodes whose text was not blocked
        safe_texts = set(result.safe_chunks)
        return [n for n, t in zip(nodes, texts, strict=True) if t in safe_texts]

    # ─── Direct access ───────────────────────────────────────────────────────

    @property
    def prompt_guard(self):
        return self._agent.prompt_guard

    @property
    def rag_guard(self):
        return self._agent.rag_guard

    @property
    def tool_guard(self):
        return self._agent.tool_guard


class _NoOpClient:
    pass
