from collections import deque
from dataclasses import dataclass, field
from typing import List
import time


@dataclass
class TurnRecord:
    message: str
    risk_score: float
    category: str
    timestamp: float = field(default_factory=time.time)


class ConversationTracker:
    """
    Sliding window conversation tracker with exponential-decay cumulative risk.
    Detects multi-turn attacks that spread across messages.
    """

    def __init__(self, window_size: int = 10, risk_threshold: float = 1.5):
        self.window_size = window_size
        self.risk_threshold = risk_threshold
        self._history: deque[TurnRecord] = deque(maxlen=window_size)

    def add_turn(self, message: str, risk_score: float, category: str) -> None:
        self._history.append(TurnRecord(message=message, risk_score=risk_score, category=category))

    @property
    def cumulative_risk(self) -> float:
        return sum(
            t.risk_score * (0.8 ** i)
            for i, t in enumerate(reversed(self._history))
        )

    @property
    def is_suspicious(self) -> bool:
        return self.cumulative_risk >= self.risk_threshold

    @property
    def recent_context(self) -> str:
        return "\n".join(t.message for t in list(self._history)[-3:])

    def boost(self, score: float) -> float:
        return min(1.0, score * 1.3) if self.is_suspicious else score

    def reset(self) -> None:
        self._history.clear()

    @property
    def history(self) -> List[TurnRecord]:
        return list(self._history)
