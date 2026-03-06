from dataclasses import dataclass, field


@dataclass
class AnzenConfig:
    # ── Prompt Guard ──────────────────────────────────────────────
    prompt_block_threshold: float = 0.85
    prompt_alert_threshold: float = 0.50
    use_ml_classifier: bool = True  # MiniLM Layer 2
    conversation_window: int = 10
    session_risk_threshold: float = 1.5

    # ── RAG Guard ─────────────────────────────────────────────────
    rag_block_threshold: float = 0.80
    rag_alert_threshold: float = 0.45
    rag_relevance_threshold: float = 0.20  # min cosine sim to query
    rag_max_instruction_score: float = 0.60  # max allowed injection score in chunk

    # ── Tool Guard ────────────────────────────────────────────────
    tool_allowed_list: list[str] | None = None  # None = allow all
    tool_blocked_list: list[str] = field(default_factory=list)
    tool_sensitive_params: dict[str, list[str]] = field(default_factory=dict)
    tool_rate_limit: int = 30  # max tool calls per minute per session
    tool_block_unknown: bool = False  # block tools not in allowed_list

    # ── Dashboard / Emitter ───────────────────────────────────────
    monitor_url: str | None = None
    api_key: str | None = None
    log_clean: bool = False  # also emit clean/safe events

    # ── Behavior on block ─────────────────────────────────────────
    block_message: str = "This request was blocked by Anzen."
