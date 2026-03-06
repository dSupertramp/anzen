"""
Shared event types emitted by all guards → EventBus → Dashboard
"""

import atexit
import json
import time
import urllib.request
import uuid
import threading
from dataclasses import dataclass, asdict, field
from enum import Enum
from typing import Any, Dict
from queue import Queue, Empty


class EventAction(str, Enum):
    ALLOW = "allow"
    ALERT = "alert"
    BLOCK = "block"


class GuardType(str, Enum):
    PROMPT = "prompt"
    RAG = "rag"
    TOOL = "tool"


@dataclass
class GuardEvent:
    guard_type: GuardType
    action: EventAction
    risk_score: float
    category: str
    explanation: str
    session_id: str

    # Optional context
    input_text: str | None = None  # prompt / chunk / tool name
    input_params: Dict | None = None  # tool params
    layer: int = 0
    latency_ms: float = 0.0
    confidence: float = 0.0
    cumulative_risk: float = 0.0
    metadata: Dict[str, Any] = field(default_factory=dict)

    # Auto-generated
    event_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    timestamp: float = field(default_factory=time.time)

    def to_json(self) -> str:
        d = asdict(self)
        d["guard_type"] = self.guard_type.value
        d["action"] = self.action.value
        return json.dumps(d)


# ─── EventBus ────────────────────────────────────────────────────────────────


class EventBus:
    """
    Thread-safe event bus. Guards emit events here.
    EventBus forwards to: console logger, dashboard emitter, custom callbacks.
    Non-blocking — drops events if queue is full rather than slow down the app.
    """

    def __init__(
        self, monitor_url: str | None = None, api_key: str | None = None
    ):
        self._queue: Queue[GuardEvent] = Queue(maxsize=2000)
        self._callbacks = []
        self._dashboard_url = monitor_url
        self._api_key = api_key
        self._stop = threading.Event()
        self._worker_thread = threading.Thread(target=self._worker, daemon=True)
        self._worker_thread.start()
        atexit.register(self.flush)

    def emit(self, event: GuardEvent) -> None:
        try:
            self._queue.put_nowait(event)
        except Exception:
            pass  # Never block the main thread

    def flush(self, timeout: float = 5.0) -> None:
        """Stop worker, wait for in-flight dispatch, then drain remaining events."""
        self._stop.set()
        self._worker_thread.join(timeout=min(2.0, timeout))
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            try:
                event = self._queue.get_nowait()
                self._dispatch(event)
            except Empty:
                break

    def on_event(self, callback) -> None:
        """Register a custom callback: fn(event: GuardEvent) -> None"""
        self._callbacks.append(callback)

    def _worker(self):
        while not self._stop.is_set():
            try:
                event = self._queue.get(timeout=0.5)
                self._dispatch(event)
            except Empty:
                continue
            except Exception:
                time.sleep(0.1)

    def _dispatch(self, event: GuardEvent):
        # Custom callbacks
        for cb in self._callbacks:
            try:
                cb(event)
            except Exception:
                pass

        # Dashboard HTTP push
        if self._dashboard_url:
            self._push_to_dashboard(event)

    def _push_to_dashboard(self, event: GuardEvent):
        url = f"{self._dashboard_url.rstrip('/')}/api/events"
        try:
            req = urllib.request.Request(
                url=url,
                data=event.to_json().encode(),
                headers={
                    "Content-Type": "application/json",
                    **({"X-Api-Key": self._api_key} if self._api_key else {}),
                },
                method="POST",
            )
            with urllib.request.urlopen(req, timeout=5):
                pass
        except Exception:
            # Dashboard unreachable (e.g. not running): fail silently
            pass
