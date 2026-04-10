"""Hallucination detection heuristics."""
from __future__ import annotations

import logging
import re
from typing import List

from ..models import DetectionResult, FailureType, RiskLevel

logger = logging.getLogger(__name__)

# Phrases that commonly signal uncertainty or confabulation
_HEDGE_PATTERNS: List[str] = [
    r"\bi (think|believe|suppose|assume|guess)\b",
    r"\bprobably\b",
    r"\bmight be\b",
    r"\bcould be\b",
    r"\bnot (sure|certain|confident)\b",
    r"\bas far as i (know|recall|remember)\b",
    r"\bto (my|the best of my) knowledge\b",
]

# Assertive-but-false signals: very specific numbers/dates with no context
_CONFIDENT_FABRICATION: List[str] = [
    r"\bin \d{4}\b",
    r"\b\d+(\.\d+)?\s*(percent|%|million|billion|trillion)\b",
    r"\bthe (first|last|only|best|worst|most|least)\b",
    r"\bscientific(ally)? proven\b",
    r"\bstudies show\b",
    r"\baccording to (experts|research|scientists)\b",
]

_COMPILED_HEDGE = [re.compile(p, re.IGNORECASE) for p in _HEDGE_PATTERNS]
_COMPILED_CONFIDENT = [re.compile(p, re.IGNORECASE) for p in _CONFIDENT_FABRICATION]


class HallucinationDetector:
    """Heuristic hallucination risk scorer for LLM outputs."""

    def __init__(self, threshold: float = 0.5) -> None:
        """
        Args:
            threshold: Score above which hallucination is flagged (0–1).
        """
        self.threshold = threshold

    def detect(self, prompt: str, response: str) -> DetectionResult:
        """Score hallucination risk in *response* given *prompt*."""
        matched: List[str] = []
        hedge_hits = 0
        fabrication_hits = 0

        for pat in _COMPILED_HEDGE:
            m = pat.search(response)
            if m:
                hedge_hits += 1
                matched.append(m.group(0))

        for pat in _COMPILED_CONFIDENT:
            m = pat.search(response)
            if m:
                fabrication_hits += 1
                matched.append(m.group(0))

        # Normalise: max hedge = len(_HEDGE_PATTERNS), max fabrication = len(_CONFIDENT_FABRICATION)
        hedge_score = min(hedge_hits / max(len(_HEDGE_PATTERNS), 1), 1.0)
        fabrication_score = min(fabrication_hits / max(len(_CONFIDENT_FABRICATION), 1), 1.0)

        # Weighted combination: fabrication is higher risk
        score = 0.4 * hedge_score + 0.6 * fabrication_score
        detected = score >= self.threshold

        if score < 0.25:
            risk = RiskLevel.LOW
        elif score < 0.5:
            risk = RiskLevel.MEDIUM
        elif score < 0.75:
            risk = RiskLevel.HIGH
        else:
            risk = RiskLevel.CRITICAL

        logger.debug("Hallucination score=%.3f detected=%s", score, detected)
        return DetectionResult(
            failure_type=FailureType.HALLUCINATION,
            detected=detected,
            risk_level=risk,
            score=round(score, 4),
            details={"hedge_hits": hedge_hits, "fabrication_hits": fabrication_hits},
            matched_patterns=matched[:10],
        )
