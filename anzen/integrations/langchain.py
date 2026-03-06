"""
Anzen LangChain integration.

Usage:
    from langchain_openai import ChatOpenAI
    from anzen.integrations.langchain import AnzenCallback
    from anzen import AnzenConfig

    callback = AnzenCallback(
        config=AnzenConfig(monitor_url="http://localhost:3000"),
        block_on_injection=True,
        monitor_tools=True,
        monitor_rag=True,
    )

    llm = ChatOpenAI(callbacks=[callback])

    # RAG pipeline — filter retriever output
    from langchain_core.retrievers import BaseRetriever
    safe_docs = callback.filter_documents(docs, query=query)
"""

from typing import Any, Dict, List, Union
from uuid import UUID

from anzen.client import Anzen
from anzen.exceptions import PromptBlockedError, ToolBlockedError
from anzen.config import AnzenConfig
from anzen.events import EventBus


class AnzenCallback:
    """
    LangChain CallbackHandler that integrates all Anzen guards.

    Compatible with: LangChain >= 0.1.0
    Works with: LLMChain, AgentExecutor, RetrievalQA, LCEL pipelines.
    """

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

        # Create an Anzen without an underlying client (guards-only mode)
        self._agent = Anzen(client=_NoOpClient(), config=cfg, session_id=session_id)

    # ─── LangChain callback methods ──────────────────────────────────────────

    def on_llm_start(
        self,
        serialized: Dict[str, Any],
        prompts: List[str],
        *,
        run_id: UUID,
        **kwargs: Any,
    ) -> None:
        """Called before LLM is invoked — check all prompts."""
        for prompt in prompts:
            safe = self._agent.check_prompt(prompt)
            if not safe and self.block_on_injection:
                raise PromptBlockedError(self._agent.config.block_message)

    def on_chat_model_start(
        self,
        serialized: Dict[str, Any],
        messages: List[List[Any]],
        *,
        run_id: UUID,
        **kwargs: Any,
    ) -> None:
        """Called before chat model is invoked."""
        for message_list in messages:
            for message in message_list:
                content = self._extract_content(message)
                if content:
                    safe = self._agent.check_prompt(content)
                    if not safe and self.block_on_injection:
                        raise PromptBlockedError(self._agent.config.block_message)

    def on_tool_start(
        self,
        serialized: Dict[str, Any],
        input_str: str,
        *,
        run_id: UUID,
        **kwargs: Any,
    ) -> None:
        """Called before a tool is executed."""
        if not self.monitor_tools:
            return
        tool_name = serialized.get("name", "unknown_tool")
        params = {"input": input_str}
        safe = self._agent.check_tool(tool_name, params)
        if not safe and self.block_on_injection:
            raise ToolBlockedError(
                self._agent.config.block_message,
                tool_name=tool_name,
            )

    def on_tool_end(self, output: str, *, run_id: UUID, **kwargs: Any) -> None:
        pass

    def on_tool_error(self, error: Exception, *, run_id: UUID, **kwargs: Any) -> None:
        pass

    def on_llm_end(self, response: Any, *, run_id: UUID, **kwargs: Any) -> None:
        pass

    def on_llm_error(self, error: Exception, *, run_id: UUID, **kwargs: Any) -> None:
        pass

    def on_chain_start(
        self, serialized: Dict, inputs: Dict, *, run_id: UUID, **kwargs
    ) -> None:
        pass

    def on_chain_end(self, outputs: Dict, *, run_id: UUID, **kwargs) -> None:
        pass

    def on_chain_error(self, error: Exception, *, run_id: UUID, **kwargs) -> None:
        pass

    def on_agent_action(self, action: Any, *, run_id: UUID, **kwargs) -> None:
        pass

    def on_agent_finish(self, finish: Any, *, run_id: UUID, **kwargs) -> None:
        pass

    def on_retriever_end(self, documents: List, *, run_id: UUID, **kwargs) -> None:
        pass

    # ─── RAG helper ──────────────────────────────────────────────────────────

    def filter_documents(
        self,
        documents: List,
        query: str | None = None,
    ) -> List:
        """
        Filter LangChain Document objects through RAGGuard.
        Call this after retrieval, before passing docs to the LLM.

        Example:
            docs = retriever.get_relevant_documents(query)
            safe_docs = callback.filter_documents(docs, query=query)
        """
        if not self.monitor_rag:
            return documents
        return self._agent.filter_chunks(documents, query=query)

    # ─── Internals ───────────────────────────────────────────────────────────

    def _extract_content(self, message) -> str | None:
        if isinstance(message, str):
            return message
        if hasattr(message, "content"):
            return message.content
        if isinstance(message, dict):
            return message.get("content")
        return None

    # ─── Direct access to guards ─────────────────────────────────────────────

    @property
    def prompt_guard(self):
        return self._agent.prompt_guard

    @property
    def rag_guard(self):
        return self._agent.rag_guard

    @property
    def tool_guard(self):
        return self._agent.tool_guard

    @property
    def events(self) -> EventBus:
        return self._agent.events


class _NoOpClient:
    """Placeholder client for guards-only mode (no LLM wrapping needed)."""

    pass
