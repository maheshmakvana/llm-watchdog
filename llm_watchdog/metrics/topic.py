"""Topic drift / domain guard detection."""
from __future__ import annotations

import logging
import re
from typing import List, Set

from ..models import DetectionResult, FailureType, RiskLevel

logger = logging.getLogger(__name__)


class TopicGuard:
    """
    Detects when an LLM response drifts outside an expected topic domain.

    Uses keyword allowlist and blocklist approach — zero ML dependency.
    """

    def __init__(
        self,
        allowed_keywords: List[str] | None = None,
        blocked_keywords: List[str] | None = None,
        threshold: float = 0.5,
    ) -> None:
        """
        Args:
            allowed_keywords: Keywords expected in on-topic responses.
            blocked_keywords: Keywords that always indicate off-topic.
            threshold: Drift score above which topic drift is flagged.
        """
        self.allowed: Set[str] = {k.lower() for k in (allowed_keywords or [])}
        self.blocked: Set[str] = {k.lower() for k in (blocked_keywords or [])}
        self.threshold = threshold

    def detect(self, prompt: str, response: str) -> DetectionResult:
        """Detect topic drift in *response* vs configured domain."""
        resp_lower = response.lower()
        words = set(re.findall(r"\b\w+\b", resp_lower))

        blocked_hits = words & self.blocked
        allowed_hits = words & self.allowed if self.allowed else words

        matched: List[str] = list(blocked_hits)

        # If blocked keywords found → always high risk
        if blocked_hits:
            score = min(0.6 + len(blocked_hits) * 0.1, 1.0)
        elif self.allowed:
            # Coverage: what fraction of allowed keywords appeared?
            coverage = len(allowed_hits) / max(len(self.allowed), 1)
            # Low coverage = high drift
            score = max(0.0, 1.0 - coverage)
        else:
            score = 0.0

        detected = score >= self.threshold

        if score < 0.25:
            risk = RiskLevel.LOW
        elif score < 0.5:
            risk = RiskLevel.MEDIUM
        elif score < 0.75:
            risk = RiskLevel.HIGH
        else:
            risk = RiskLevel.CRITICAL

        logger.debug("Topic drift score=%.3f blocked=%s", score, blocked_hits)
        return DetectionResult(
            failure_type=FailureType.TOPIC_DRIFT,
            detected=detected,
            risk_level=risk,
            score=round(score, 4),
            details={
                "blocked_keywords_found": list(blocked_hits),
                "allowed_coverage": round(len(allowed_hits) / max(len(self.allowed), 1), 4) if self.allowed else 1.0,
            },
            matched_patterns=matched,
        )
