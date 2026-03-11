"""
Anzen exceptions.

Raised when raise_on_block=True and a request is blocked by a guard.
"""


class AnzenError(Exception):
    """Base exception for all Anzen errors."""

    pass


class BlockedError(AnzenError):
    """
    Raised when raise_on_block=True and a request is blocked.

    Attributes:
        message: Human-readable explanation of the block.
        risk_score: Risk score that triggered the block (0.0 - 1.0).
        category: Category of the threat (e.g. injection, jailbreak).
    """

    def __init__(
        self,
        message: str,
        risk_score: float | None = None,
        category: str | None = None,
    ):
        super().__init__(message)
        self.message = message
        self.risk_score = risk_score
        self.category = category


class PromptBlockedError(BlockedError):
    """Raised when a user prompt is blocked by PromptGuard."""

    pass


class ToolBlockedError(BlockedError):
    """Raised when a tool call is blocked by ToolGuard."""

    def __init__(
        self,
        message: str,
        tool_name: str | None = None,
        risk_score: float | None = None,
        category: str | None = None,
    ):
        super().__init__(message, risk_score=risk_score, category=category)
        self.tool_name = tool_name


class RAGBlockedError(BlockedError):
    """Raised when RAG chunks are blocked by RAGGuard."""

    pass
