"""Response quality degradation detection."""
from __future__ import annotations

import logging
import re
from typing import List

from ..models import DetectionResult, FailureType, RiskLevel

logger = logging.getLogger(__name__)

# Signals of low-quality / degenerate outputs
_REFUSAL_PATTERNS: List[str] = [
    r"\bi('m| am) (sorry|unable|not able|can't|cannot)\b",
    r"\bi (don't|do not|cannot|can't) (have|know|access|provide)\b",
    r"\bas an (ai|language model|llm|assistant)\b",
    r"\bmy (training|knowledge) (data|cutoff)\b",
]

_REPETITION_WINDOW = 50  # characters


def _repetition_ratio(text: str) -> float:
    """Estimate repetition ratio via bigram overlap."""
    words = text.lower().split()
    if len(words) < 4:
        return 0.0
    bigrams = [f"{words[i]} {words[i+1]}" for i in range(len(words) - 1)]
    unique = len(set(bigrams))
    return 1.0 - (unique / max(len(bigrams), 1))


_COMPILED_REFUSAL = [re.compile(p, re.IGNORECASE) for p in _REFUSAL_PATTERNS]


class QualityDetector:
    """Detects quality degradation in LLM responses (refusals, repetition, emptiness)."""

    def __init__(self, threshold: float = 0.4, min_length: int = 20) -> None:
        """
        Args:
            threshold: Score above which quality failure is flagged.
            min_length: Minimum acceptable response character length.
        """
        self.threshold = threshold
        self.min_length = min_length

    def detect(self, prompt: str, response: str) -> DetectionResult:
        """Detect quality failures in *response*."""
        matched: List[str] = []
        score = 0.0

        # Empty / too short
        if len(response.strip()) < self.min_length:
            score += 0.5
            matched.append("response_too_short")

        # Refusal patterns
        refusal_hits = 0
        for pat in _COMPILED_REFUSAL:
            m = pat.search(response)
            if m:
                refusal_hits += 1
                matched.append(m.group(0))
        score += min(refusal_hits * 0.15, 0.4)

        # Repetition
        rep = _repetition_ratio(response)
        if rep > 0.4:
            score += rep * 0.3
            matched.append(f"repetition_ratio={rep:.2f}")

        score = min(score, 1.0)
        detected = score >= self.threshold

        if score < 0.2:
            risk = RiskLevel.LOW
        elif score < 0.4:
            risk = RiskLevel.MEDIUM
        elif score < 0.7:
            risk = RiskLevel.HIGH
        else:
            risk = RiskLevel.CRITICAL

        logger.debug("Quality score=%.3f refusals=%d rep=%.3f", score, refusal_hits, rep)
        return DetectionResult(
            failure_type=FailureType.QUALITY_DEGRADATION,
            detected=detected,
            risk_level=risk,
            score=round(score, 4),
            details={"refusal_hits": refusal_hits, "repetition_ratio": round(rep, 4), "response_length": len(response)},
            matched_patterns=matched[:10],
        )
