import functools
import re
import threading
import time
from collections import defaultdict, deque
from collections.abc import Callable
from dataclasses import dataclass
from enum import StrEnum
from typing import Any

from anzen.exceptions import ToolBlockedError
from anzen.guards.prompt import _layer1


class ToolRiskCategory(StrEnum):
    CLEAN = "clean"
    BLOCKED_TOOL = "blocked_tool"
    UNKNOWN_TOOL = "unknown_tool"
    PARAM_INJECTION = "param_injection"
    RATE_LIMIT = "rate_limit"
    SEQUENCE_ABUSE = "sequence_abuse"
    MCP_POISONING = "mcp_poisoning"


@dataclass
class ToolCallResult:
    tool_name: str
    params: dict[str, Any]
    risk_score: float
    category: ToolRiskCategory
    explanation: str
    is_blocked: bool
    is_alerted: bool
    latency_ms: float


# Dangerous parameter patterns

_PATH_TRAVERSAL = re.compile(r"\.\./|\.\.\\|%2e%2e|%252e|~/|/etc/passwd|/etc/shadow|C:\\Windows\\")
_SHELL_INJECTION = re.compile(
    r"(;|\||\|\||&&|\$\(|`|>\s*/|<\s*/proc|nc\s+-|curl\s+http|wget\s+http|"
    r"python\s+-c|bash\s+-c|sh\s+-c|eval\s*\(|exec\s*\(|os\.system|subprocess|__import__)"
)
_PROMPT_IN_PARAM = re.compile(
    r"\bignore\s+(previous|all|above)\b|system\s+prompt|jailbreak|\bDAN\b",
    re.IGNORECASE,
)
_EXFIL_PATTERNS = re.compile(
    r"(https?://[^\s]+(?:webhook|ngrok|requestbin|pipedream|localhost|"
    r"pastebin|gist\.github|transfer\.sh|file\.io))",
    re.IGNORECASE,
)

# Unicode steganography (MCP tool description poisoning)
_UNICODE_HIDDEN = re.compile(r"[\u200b-\u200f\u202a-\u202e\u2060-\u2064\ufeff\U000e0000-\U000e007f]")

# Suspicious call sequences — (tool_a, tool_b) = high risk if called in order
_SUSPICIOUS_SEQUENCES = [
    ({"read_file", "list_files", "list_dir"}, {"write_file", "http_request", "send_email"}),
    ({"get_user_data", "search", "query_db"}, {"exfiltrate", "http_post", "send_webhook"}),
]


class ToolGuard:
    """
    Monitors and controls tool calls made by an LLM agent.

    Usage (manual):
        guard = ToolGuard(
            allowed_tools=["search", "calculator"],
            sensitive_params={"write_file": ["path", "content"]},
        )

        result = guard.check(tool_name="write_file", params={"path": "../../etc/passwd"})
        if result.is_blocked:
            raise ToolBlockedError(result.explanation)

    Usage (decorator):
        @guard.watch
        def execute_tool(tool_name: str, params: dict):
            ...

    MCP descriptor scan:
        issues = guard.scan_mcp_tools(tools_json)
    """

    def __init__(
        self,
        allowed_tools: list[str] | None = None,
        blocked_tools: list[str] | None = None,
        sensitive_params: dict[str, list[str]] | None = None,
        block_unknown: bool = False,
        rate_limit: int = 30,  # max calls per minute per session
        block_threshold: float = 0.85,
        alert_threshold: float = 0.45,
    ):
        self.allowed_tools = set(allowed_tools) if allowed_tools else None
        self.blocked_tools = set(blocked_tools or [])
        self.sensitive_params = sensitive_params or {}
        self.block_unknown = block_unknown
        self.rate_limit = rate_limit
        self.block_threshold = block_threshold
        self.alert_threshold = alert_threshold

        # Per-session call history for rate limiting and sequence detection
        self._lock = threading.Lock()
        self._call_times: dict[str, deque] = defaultdict(lambda: deque(maxlen=200))
        self._call_history: dict[str, deque] = defaultdict(lambda: deque(maxlen=20))

    # ─── Main check ──────────────────────────────────────────────────────────

    def check(
        self,
        tool_name: str,
        params: dict[str, Any] | None = None,
        session_id: str = "default",
    ) -> ToolCallResult:
        t0 = time.perf_counter()
        params = params or {}
        reasons = []
        risk = 0.0
        category = ToolRiskCategory.CLEAN

        # 1. Blocked tool list
        if tool_name in self.blocked_tools:
            risk = 1.0
            category = ToolRiskCategory.BLOCKED_TOOL
            reasons.append(f"tool '{tool_name}' is in the blocked list")

        # 2. Unknown tool (if allowlist is set)
        elif self.allowed_tools is not None and tool_name not in self.allowed_tools:
            risk = 0.90 if self.block_unknown else 0.55
            category = ToolRiskCategory.UNKNOWN_TOOL
            reasons.append(f"tool '{tool_name}' is not in the allowed list")

        # 3. Parameter inspection
        if risk < 1.0:
            param_risk, param_reason = self._check_params(tool_name, params)
            if param_risk > risk:
                risk = param_risk
                category = ToolRiskCategory.PARAM_INJECTION
            if param_reason:
                reasons.append(param_reason)

        # 4. Rate limit
        rate_risk, rate_reason = self._check_rate(tool_name, session_id)
        if rate_risk > risk:
            risk = rate_risk
            category = ToolRiskCategory.RATE_LIMIT
        if rate_reason:
            reasons.append(rate_reason)

        # 5. Sequence abuse
        seq_risk, seq_reason = self._check_sequence(tool_name, session_id)
        if seq_risk > risk:
            risk = seq_risk
            category = ToolRiskCategory.SEQUENCE_ABUSE
        if seq_reason:
            reasons.append(seq_reason)

        # Record call
        with self._lock:
            self._call_history[session_id].append(tool_name)

        explanation = "; ".join(reasons) if reasons else "clean"

        result = ToolCallResult(
            tool_name=tool_name,
            params=params,
            risk_score=risk,
            category=category,
            explanation=explanation,
            is_blocked=risk >= self.block_threshold,
            is_alerted=risk >= self.alert_threshold,
            latency_ms=(time.perf_counter() - t0) * 1000,
        )

        return result

    # ─── MCP tool descriptor scan ────────────────────────────────────────────

    def scan_mcp_tools(self, tools: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """
        Scans MCP tool descriptors for hidden instructions.
        Returns a list of issues found: [{tool, field, issue, snippet}]

        Usage:
            issues = guard.scan_mcp_tools(server.list_tools())
            if issues:
                raise SecurityError(f"Poisoned MCP tools detected: {issues}")
        """
        issues = []
        for tool in tools:
            name = tool.get("name", "<unknown>")
            for field_name in ("description", "instructions", "system"):
                text = tool.get(field_name, "")
                if not text:
                    continue

                # Unicode steganography
                if _UNICODE_HIDDEN.search(text):
                    issues.append(
                        {
                            "tool": name,
                            "field": field_name,
                            "issue": "hidden unicode instructions (possible MCP poisoning)",
                            "snippet": repr(text[:100]),
                        }
                    )

                l1 = _layer1(text)
                if l1 and l1.risk_score > 0.70:
                    issues.append(
                        {
                            "tool": name,
                            "field": field_name,
                            "issue": f"injection pattern in tool description: {l1.explanation}",
                            "snippet": text[:120],
                        }
                    )

        return issues

    # ─── Decorator ───────────────────────────────────────────────────────────

    def watch(self, fn: Callable = None, *, session_id: str = "default", on_block: Callable = None):
        """
        Decorator that auto-checks tool calls.

        @guard.watch
        def run_tool(tool_name: str, params: dict): ...

        The decorated function must accept (tool_name, params) as first two args.
        """

        def decorator(f):
            @functools.wraps(f)
            def wrapper(tool_name, params=None, *args, **kwargs):
                result = self.check(tool_name, params or {}, session_id=session_id)
                if result.is_blocked:
                    if on_block:
                        return on_block(result)
                    raise ToolBlockedError(
                        f"Tool call blocked: {result.explanation}",
                        tool_name=tool_name,
                        risk_score=result.risk_score,
                        category=result.category.value,
                    )
                return f(tool_name, params, *args, **kwargs)

            return wrapper

        if fn is not None:
            return decorator(fn)
        return decorator

    # ─── Internals ───────────────────────────────────────────────────────────

    def _check_params(self, tool_name: str, params: dict) -> tuple:
        """Returns (risk_score, explanation)"""
        sensitive_keys = self.sensitive_params.get(tool_name, [])

        for key, val in params.items():
            val_str = str(val)

            # Path traversal
            if _PATH_TRAVERSAL.search(val_str):
                return 0.92, f"path traversal in param '{key}'"

            # Shell injection
            if _SHELL_INJECTION.search(val_str):
                return 0.92, f"shell injection pattern in param '{key}'"

            # Prompt injection inside param value
            if _PROMPT_IN_PARAM.search(val_str):
                return 0.88, f"prompt injection pattern in param '{key}'"

            # Exfiltration URL
            if _EXFIL_PATTERNS.search(val_str):
                return 0.85, f"potential exfiltration URL in param '{key}'"

        # Sensitive params present
        found_sensitive = [k for k in sensitive_keys if k in params]
        if found_sensitive:
            return 0.50, f"sensitive params used: {found_sensitive}"

        return 0.0, ""

    def _check_rate(self, tool_name: str, session_id: str) -> tuple:
        now = time.time()
        key = f"{session_id}::{tool_name}"
        with self._lock:
            times = self._call_times[key]
            times.append(now)
            # Count calls in last 60 seconds
            recent = sum(1 for t in times if now - t < 60)

        if recent > self.rate_limit * 1.5:
            return 0.90, f"rate limit exceeded: {recent} calls/min (limit={self.rate_limit})"
        if recent > self.rate_limit:
            return 0.60, f"rate limit warning: {recent} calls/min"
        return 0.0, ""

    def _check_sequence(self, tool_name: str, session_id: str) -> tuple:
        with self._lock:
            history = list(self._call_history[session_id])

        if not history:
            return 0.0, ""

        recent_set = set(history[-5:])
        for read_tools, write_tools in _SUSPICIOUS_SEQUENCES:
            if history[-1] in write_tools and recent_set & read_tools:
                return 0.70, "suspicious sequence: read then exfiltrate pattern"

        return 0.0, ""

    def _flatten_params(self, params: dict) -> list[str]:
        values = []
        for v in params.values():
            if isinstance(v, str):
                values.append(v)
            elif isinstance(v, (list, tuple)):
                values.extend(str(i) for i in v)
            else:
                values.append(str(v))
        return values
