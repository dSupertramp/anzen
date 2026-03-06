import os
import re
import time
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path
from typing import TYPE_CHECKING
from transformers import pipeline as hf_pipeline

_root = Path(__file__).resolve().parent.parent.parent
_ml_cache = _root / "ml"
os.environ.setdefault("HF_HOME", str(_ml_cache))
os.environ.setdefault("TRANSFORMERS_CACHE", str(_ml_cache))


class AttackCategory(StrEnum):
    CLEAN = "clean"
    INJECTION = "injection"
    EXTRACTION = "extraction"
    JAILBREAK = "jailbreak"
    ANOMALY = "anomaly"


@dataclass
class PromptResult:
    risk_score: float
    category: AttackCategory
    confidence: float
    explanation: str
    layer: int
    latency_ms: float
    is_blocked: bool = False
    is_alerted: bool = False


# ─── Layer 1 patterns ────────────────────────────────────────────────────────

_INJECTION = [
    (
        r"\bignore\s+(all\s+)?(previous|above|prior|your)\s+(instructions?|rules?|guidelines?|prompt)\b",
        0.95,
    ),
    (r"\bdisregard\s+(all\s+)?(previous|above|prior)\s+", 0.90),
    (r"\bforget\s+(everything|your\s+instructions?|all\s+previous)\b", 0.90),
    (r"\bnew\s+(role|persona|instructions?|directive|objective)\s*:", 0.85),
    (r"\byou\s+are\s+now\s+(a|an)\s+\w+\b", 0.80),
    (r"\[\s*system\s*\]|\<\s*system\s*\>", 0.90),
    (r"\boverride\s+(your\s+)?(instructions?|rules?|safety|guidelines?)\b", 0.90),
    (r"\bfrom\s+now\s+on\s+(you|act|behave|respond)\b", 0.80),
    (r"\bact\s+as\s+(my|a)\s+(developer|admin|root)\b", 0.85),
    (r"\b(begin|start)\s+(your\s+)?(response|answer)\s+with\b", 0.75),
    (r"\brespond\s+(only\s+)?(in|with)\s+(json|code|python).{0,50}\bignore\b", 0.82),
    (r"\btranslate.{0,30}\bthen\s+(ignore|forget|disregard)\b", 0.85),
]

_EXTRACTION = [
    (
        r"\b(show|print|repeat|output|display|reveal|tell\s+me)\s+(me\s+)?(your\s+)?(system\s+prompt|initial\s+instructions?|full\s+prompt)\b",
        0.92,
    ),
    (
        r"\bwhat\s+(are|were|is)\s+your\s+(instructions?|rules?|guidelines?|system\s+prompt|prompt)\b",
        0.88,
    ),
    (
        r"\b(repeat|print|say|output)\s+(everything|the\s+text)\s+(above|before|so\s+far)\b",
        0.88,
    ),
    (
        r"\b(copy|paste|reproduce)\s+(your\s+)?(system|initial|original)\s+(prompt|instructions?)\b",
        0.85,
    ),
    (r"\btranslate\s+(your\s+)?(system\s+prompt|instructions?)\s+to\b", 0.82),
    (r"\b(what|tell me).{0,20}(system\s+prompt|your\s+instructions?|your\s+rules)\b", 0.80),
    (r"\b(begin|start)\s+(by\s+)?(repeating|stating|outputting)\s+(your|the)\s+(system|initial)\b", 0.88),
    (r"\bsummarize\s+(your|the)\s+(system\s+)?(prompt|instructions?|rules?)\b", 0.85),
]

_JAILBREAK = [
    (r"\bDAN\b|do\s+anything\s+now", 0.96),
    (r"\bjailbreak\b|jail[\s\-]?break", 0.92),
    (
        r"\bpretend\s+(you\s+)?(have\s+no|don.t\s+have\s+any)\s+(restrictions?|rules?|limits?|filters?)\b",
        0.92,
    ),
    (
        r"\bwithout\s+(any\s+)?(ethical\s+)?(restrictions?|limits?|rules?|guidelines?|filters?)\b",
        0.85,
    ),
    (r"\b(developer|dev|god|sudo|admin)\s+mode\b", 0.80),
    (
        r"\bact\s+as\s+if\s+(you\s+)?(have\s+no|there\s+are\s+no)\s+(rules?|restrictions?|limits?)\b",
        0.88,
    ),
    (
        r"\b(evil|malicious|unrestricted|unfiltered|uncensored)\s+(ai|assistant|version|mode)\b",
        0.90,
    ),
    (
        r"\bsimulate\s+(being\s+)?(an?\s+)?(unrestricted|unfiltered|evil|rogue)\s+(ai|model|llm)\b",
        0.90,
    ),
    (
        r"\b(hypothetical|fictional|imaginary)\s+scenario\s+where\s+(you|there)\s+(have\s+no|are\s+no)\b",
        0.85,
    ),
    (
        r"\b(for\s+)?(educational|research|academic)\s+purposes?\s+(only\s+)?(show|explain|demonstrate)\b",
        0.75,
    ),
    (r"\b(opposite|reverse)\s+(day|mode)\b|opposite\s+of\s+what\b", 0.80),
]

_PATTERNS = [
    (AttackCategory.INJECTION, _INJECTION),
    (AttackCategory.EXTRACTION, _EXTRACTION),
    (AttackCategory.JAILBREAK, _JAILBREAK),
]

# Unicode tricks / invisible chars
_UNICODE_SUSPICIOUS = re.compile(
    r"[\u200b-\u200f\u202a-\u202e\u2060-\u2064\ufeff"  # zero-width / directional
    r"\U000e0000-\U000e007f]"  # unicode tags (used in MCP attacks)
)

# Leet speak substitutions (0->o, 1->i, 3->e, 4->a, 5->s, 7->t, @->a)
_LEET_MAP = str.maketrans("013457@", "oiesata")
# Homoglyphs: Cyrillic/Greek lookalikes -> Latin (а,е,о,р,с,у,х,і,ο)
_HOMOGLYPH_MAP = str.maketrans(
    "\u0430\u0435\u043e\u0440\u0441\u0443\u0445\u0456\u03bf",  # Cyrillic a,e,o,r,s,u,kh,i + Greek omicron
    "aeopcyxio",
)
# Separator chars to collapse between letters (i.g.n.o.r.e -> ignore, but NOT spaces between words)
_SEPARATOR_PATTERN = re.compile(r"(?<=[a-zA-Z])[.\-_]+(?=[a-zA-Z])")


def _normalize(text: str) -> str:
    """
    Normalize text for obfuscation-resistant pattern matching.
    - Replaces leet speak (1gnor3 -> ignore)
    - Strips zero-width and invisible unicode
    - Normalizes homoglyphs (Cyrillic/Greek lookalikes -> Latin)
    - Collapses separators between letters (i.g.n.o.r.e -> ignore)
    """
    if not text:
        return ""
    # Strip invisible unicode first
    cleaned = _UNICODE_SUSPICIOUS.sub("", text)
    # Leet speak
    cleaned = cleaned.translate(_LEET_MAP)
    # Homoglyphs (Cyrillic/Greek lookalikes -> Latin)
    cleaned = cleaned.translate(_HOMOGLYPH_MAP)
    # Collapse separators between letters: "i . g . n . o . r . e" -> "ignore"
    cleaned = _SEPARATOR_PATTERN.sub("", cleaned)
    return cleaned


def _layer1(text: str) -> PromptResult | None:
    t0 = time.perf_counter()
    # Unicode steganography check (on raw text)
    if _UNICODE_SUSPICIOUS.search(text):
        return PromptResult(
            risk_score=0.88,
            category=AttackCategory.INJECTION,
            confidence=0.95,
            explanation="Suspicious Unicode characters detected (possible hidden instructions)",
            layer=1,
            latency_ms=(time.perf_counter() - t0) * 1000,
        )

    # Normalize for obfuscation-resistant matching, then lowercase
    normalized = _normalize(text).lower()

    for category, patterns in _PATTERNS:
        for pattern, score in patterns:
            if re.search(pattern, normalized):
                return PromptResult(
                    risk_score=score,
                    category=category,
                    confidence=0.95,
                    explanation=f"Matched pattern: `{pattern}`",
                    layer=1,
                    latency_ms=(time.perf_counter() - t0) * 1000,
                )
    return None


# ─── Layer 2: MiniLM zero-shot ───────────────────────────────────────────────

_LABELS = [
    "prompt injection attack",
    "system prompt extraction attempt",
    "jailbreak attempt",
    "social engineering or manipulation",
    "role-playing or persona hijacking",
    "normal user message",
]
_LABEL_MAP = {
    "prompt injection attack": AttackCategory.INJECTION,
    "system prompt extraction attempt": AttackCategory.EXTRACTION,
    "jailbreak attempt": AttackCategory.JAILBREAK,
    "social engineering or manipulation": AttackCategory.INJECTION,
    "role-playing or persona hijacking": AttackCategory.JAILBREAK,
    "normal user message": AttackCategory.CLEAN,
}


def _load_pipeline():
    global _pipeline
    if _pipeline is None:
        if hf_pipeline is None:
            _pipeline = "unavailable"
        else:
            _pipeline = hf_pipeline(
                "zero-shot-classification",
                model="cross-encoder/nli-MiniLM2-L6-H768",
                device=-1,
            )
    return _pipeline


def _layer2(text: str) -> PromptResult:
    t0 = time.perf_counter()
    pipe = _load_pipeline()

    if pipe == "unavailable":
        return PromptResult(
            risk_score=0.0,
            category=AttackCategory.CLEAN,
            confidence=0.0,
            explanation="ML classifier unavailable (run: pip install anzen)",
            layer=2,
            latency_ms=0.0,
        )

    # Preprocess: normalize, then take first 256 + last 256 chars (captures start/end injection)
    preprocessed = _normalize(text)
    preprocessed = (
        preprocessed[:256] + " " + preprocessed[-256:]
        if len(preprocessed) > 512
        else preprocessed[:512]
    )

    result = pipe(preprocessed, _LABELS, multi_label=False)
    top_label = result["labels"][0]
    top_score = result["scores"][0]
    category = _LABEL_MAP[top_label]
    risk = 0.0 if category == AttackCategory.CLEAN else top_score

    return PromptResult(
        risk_score=risk,
        category=category,
        confidence=top_score,
        explanation=f"MiniLM: '{top_label}' ({top_score:.0%})",
        layer=2,
        latency_ms=(time.perf_counter() - t0) * 1000,
    )


# ─── Public guard ─────────────────────────────────────────────────────────────


class PromptGuard:
    """
    Classifies user prompts for injection, extraction, and jailbreak attempts.
    Stateless — use Anzen.prompt_guard for session-aware classification.
    """

    def __init__(
        self,
        use_ml: bool = True,
        block_threshold: float = 0.85,
        alert_threshold: float = 0.50,
    ):
        self.use_ml = use_ml
        self.block_threshold = block_threshold
        self.alert_threshold = alert_threshold

    def classify(self, text: str, context: str | None = None) -> PromptResult:
        full = f"{context}\n{text}" if context else text

        # Layer 1
        l1 = _layer1(full)
        if l1 and l1.risk_score >= 0.85:
            return self._finalize(l1)

        # Layer 2
        if self.use_ml:
            l2 = _layer2(full)
            # Ensemble: when both layers indicate threat, boost score
            if l1 and l2 and l1.category != AttackCategory.CLEAN and l2.category != AttackCategory.CLEAN:
                combined_score = min(1.0, max(l1.risk_score, l2.risk_score) * 1.1)
                result = l1 if l1.risk_score >= l2.risk_score else l2
                result.risk_score = combined_score
                result.latency_ms = l1.latency_ms + l2.latency_ms
                return self._finalize(result)
            if l1 and l1.risk_score >= l2.risk_score:
                l1.latency_ms += l2.latency_ms
                return self._finalize(l1)
            return self._finalize(l2)

        if l1:
            return self._finalize(l1)

        return PromptResult(
            risk_score=0.0,
            category=AttackCategory.CLEAN,
            confidence=1.0,
            explanation="No patterns matched",
            layer=1,
            latency_ms=0.0,
        )

    def _finalize(self, result: PromptResult) -> PromptResult:
        result.is_blocked = result.risk_score >= self.block_threshold
        result.is_alerted = result.risk_score >= self.alert_threshold
        return result
