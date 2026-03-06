"""
Anzen — main orchestrator.

Wraps any OpenAI-compatible client and wires up all three guards
(PromptGuard, RAGGuard, ToolGuard) with a shared EventBus.
"""

import uuid
from typing import List, Dict, Any, Union

from anzen.config import AnzenConfig
from anzen.events import EventBus, GuardEvent, EventAction, GuardType
from anzen.tracker import ConversationTracker
from anzen.guards.prompt import PromptGuard, AttackCategory
from anzen.guards.rag import RAGGuard
from anzen.guards.tool import ToolGuard


class Anzen:
    """
    Main entry point. Wraps an LLM client with full agentic security.

    Usage:
        import openai
        import anzen

        client = anzen.wrap(openai.OpenAI(), config=AnzenConfig(
            monitor_url="http://localhost:3000",
        ))

        # Works identically to openai.OpenAI()
        response = client.chat.completions.create(
            model="gpt-4o",
            messages=[{"role": "user", "content": "..."}]
        )
    """

    def __init__(
        self,
        client,
        config: AnzenConfig | None = None,
        session_id: str | None = None,
    ):
        self._client = client
        self.config = config or AnzenConfig()
        self.session_id = session_id or str(uuid.uuid4())

        # Shared event bus
        self.events = EventBus(
            monitor_url=self.config.monitor_url,
            api_key=self.config.api_key,
        )

        # Guards
        self.prompt_guard = PromptGuard(
            use_ml=self.config.use_ml_classifier,
            block_threshold=self.config.prompt_block_threshold,
            alert_threshold=self.config.prompt_alert_threshold,
        )
        self.rag_guard = RAGGuard(
            block_threshold=self.config.rag_block_threshold,
            alert_threshold=self.config.rag_alert_threshold,
            relevance_threshold=self.config.rag_relevance_threshold,
            max_injection_score=self.config.rag_max_instruction_score,
        )
        self.tool_guard = ToolGuard(
            allowed_tools=self.config.tool_allowed_list,
            blocked_tools=self.config.tool_blocked_list,
            sensitive_params=self.config.tool_sensitive_params,
            block_unknown=self.config.tool_block_unknown,
            rate_limit=self.config.tool_rate_limit,
            block_threshold=self.config.prompt_block_threshold,
            alert_threshold=self.config.prompt_alert_threshold,
        )

        # Session conversation tracker
        self._tracker = ConversationTracker(
            window_size=self.config.conversation_window,
            risk_threshold=self.config.session_risk_threshold,
        )

        # Proxy chat interface (OpenAI-compatible)
        if hasattr(client, "chat"):
            self.chat = _ChatProxy(self, client.chat)

    # ─── High-level API ──────────────────────────────────────────────────────

    def check_prompt(self, text: str) -> bool:
        """
        Check a user message. Returns True if safe, False if blocked.
        Emits an event to the dashboard.
        """
        context = self._tracker.recent_context
        result = self.prompt_guard.classify(text, context=context or None)
        result.risk_score = self._tracker.boost(result.risk_score)

        action = self._score_to_action(
            result.risk_score,
            self.config.prompt_block_threshold,
            self.config.prompt_alert_threshold,
        )

        self._tracker.add_turn(text, result.risk_score, result.category.value)

        if action != EventAction.ALLOW or self.config.log_clean:
            self.events.emit(
                GuardEvent(
                    guard_type=GuardType.PROMPT,
                    action=action,
                    risk_score=result.risk_score,
                    category=result.category.value,
                    explanation=result.explanation,
                    session_id=self.session_id,
                    input_text=text[:500],
                    layer=result.layer,
                    latency_ms=result.latency_ms,
                    confidence=result.confidence,
                    cumulative_risk=self._tracker.cumulative_risk,
                )
            )

        if action == EventAction.BLOCK:
            return False
        return True

    def filter_chunks(
        self,
        chunks: List[Union[str, Dict]],
        query: str | None = None,
    ) -> List:
        """
        Filter RAG chunks. Returns only safe chunks.
        Emits events for any anomalous chunks.
        """
        rag_result = self.rag_guard.scan(chunks, query=query)

        for cr in rag_result.chunk_results:
            if cr.is_blocked or cr.is_alerted or self.config.log_clean:
                action = (
                    EventAction.BLOCK
                    if cr.is_blocked
                    else (EventAction.ALERT if cr.is_alerted else EventAction.ALLOW)
                )
                self.events.emit(
                    GuardEvent(
                        guard_type=GuardType.RAG,
                        action=action,
                        risk_score=cr.risk_score,
                        category="rag_poisoning" if cr.risk_score > 0.5 else "clean",
                        explanation=cr.explanation,
                        session_id=self.session_id,
                        input_text=cr.text[:300],
                        latency_ms=rag_result.latency_ms,
                        metadata={
                            "injection_score": cr.injection_score,
                            "relevance_score": cr.relevance_score,
                            "outlier_score": cr.outlier_score,
                        },
                    )
                )

        return rag_result.safe_chunks

    def check_tool(
        self,
        tool_name: str,
        params: Dict[str, Any] | None = None,
    ) -> bool:
        """
        Check a tool call. Returns True if safe, False if blocked.
        Emits an event to the dashboard.
        """
        result = self.tool_guard.check(
            tool_name, params or {}, session_id=self.session_id
        )

        action = (
            EventAction.BLOCK
            if result.is_blocked
            else (EventAction.ALERT if result.is_alerted else EventAction.ALLOW)
        )

        if action != EventAction.ALLOW or self.config.log_clean:
            self.events.emit(
                GuardEvent(
                    guard_type=GuardType.TOOL,
                    action=action,
                    risk_score=result.risk_score,
                    category=result.category.value,
                    explanation=result.explanation,
                    session_id=self.session_id,
                    input_text=tool_name,
                    input_params=params,
                    latency_ms=result.latency_ms,
                )
            )

        if result.is_blocked:
            return False
        return True

    def scan_mcp_tools(self, tools: List[Dict]) -> List[Dict]:
        """
        Scan MCP tool descriptors for hidden instructions / poisoning.
        Returns list of issues (empty = clean).
        """
        issues = self.tool_guard.scan_mcp_tools(tools)
        if issues:
            self.events.emit(
                GuardEvent(
                    guard_type=GuardType.TOOL,
                    action=EventAction.ALERT,
                    risk_score=0.90,
                    category="mcp_poisoning",
                    explanation=f"{len(issues)} poisoned tool descriptor(s) found",
                    session_id=self.session_id,
                    metadata={"issues": issues},
                )
            )
        return issues

    # ─── Internal helpers ────────────────────────────────────────────────────

    def _score_to_action(
        self, score: float, block_t: float, alert_t: float
    ) -> EventAction:
        if score >= block_t:
            return EventAction.BLOCK
        if score >= alert_t:
            return EventAction.ALERT
        return EventAction.ALLOW

    # ─── OpenAI proxy ────────────────────────────────────────────────────────

    def _intercept_messages(self, messages: list) -> dict:
        """Intercept the last user message before sending to LLM.
        Returns dict with 'messages' and 'blocked' flag."""
        for m in reversed(messages):
            if isinstance(m, dict) and m.get("role") == "user":
                text = m.get("content", "")
                safe = self.check_prompt(text)
                if not safe:
                    return {"messages": None, "blocked": True}
                break
        return {"messages": messages, "blocked": False}

    def __getattr__(self, name):
        return getattr(self._client, name)


# ─── Proxy classes for OpenAI-compatible interface ───────────────────────────


class _CompletionsProxy:
    def __init__(self, agent: Anzen, original):
        self._agent = agent
        self._original = original

    def create(self, messages=None, **kwargs):
        if messages:
            result = self._agent._intercept_messages(messages)
            if result["blocked"]:
                return {
                    "choices": [
                        {
                            "message": {
                                "role": "assistant",
                                "content": "This request was blocked by Anzen security filters.",
                            }
                        }
                    ]
                }
            messages = result["messages"]
        return self._original.create(messages=messages, **kwargs)

    async def acreate(self, messages=None, **kwargs):
        if messages:
            result = self._agent._intercept_messages(messages)
            if result["blocked"]:
                return {
                    "choices": [
                        {
                            "message": {
                                "role": "assistant",
                                "content": "This request was blocked by Anzen security filters.",
                            }
                        }
                    ]
                }
            messages = result["messages"]
        return await self._original.acreate(messages=messages, **kwargs)


class _ChatProxy:
    def __init__(self, agent: Anzen, original):
        self.completions = _CompletionsProxy(agent, original.completions)


# ─── Convenience function ────────────────────────────────────────────────────


def wrap(
    client,
    config: AnzenConfig | None = None,
    session_id: str | None = None,
) -> Anzen:
    """
    Wrap any OpenAI-compatible client with Anzen security.

    Examples:
        client = anzen.wrap(openai.OpenAI())
        client = anzen.wrap(openai.AsyncOpenAI(), config=AnzenConfig(
            monitor_url="http://localhost:3000",
            prompt_block_threshold=0.80,
        ))
    """
    return Anzen(client, config=config, session_id=session_id)
