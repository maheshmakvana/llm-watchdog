"""Core PromptWatcher — orchestrates all detectors."""
from __future__ import annotations

import asyncio
import logging
import time
from typing import Any, Callable, Dict, List, Optional

from .exceptions import AlertDeliveryError
from .models import AlertEvent, DetectionResult, FailureType, RiskLevel, WatchResult
from .metrics import HallucinationDetector, PIIDetector, TopicGuard, ToxicityDetector, QualityDetector

logger = logging.getLogger(__name__)

_RISK_ORDER = {RiskLevel.LOW: 0, RiskLevel.MEDIUM: 1, RiskLevel.HIGH: 2, RiskLevel.CRITICAL: 3}


def _max_risk(levels: List[RiskLevel]) -> RiskLevel:
    """Return the highest risk level from a list."""
    if not levels:
        return RiskLevel.LOW
    return max(levels, key=lambda r: _RISK_ORDER[r])


class PromptWatcher:
    """
    Production-grade LLM response monitor.

    Runs hallucination, PII, topic, toxicity, and quality detectors
    on every LLM response and fires alert callbacks when thresholds breach.
    """

    def __init__(
        self,
        hallucination_threshold: float = 0.5,
        pii_threshold: float = 0.1,
        toxicity_threshold: float = 0.3,
        quality_threshold: float = 0.4,
        topic_allowed: Optional[List[str]] = None,
        topic_blocked: Optional[List[str]] = None,
        topic_threshold: float = 0.5,
        block_on_critical: bool = False,
    ) -> None:
        self._hall = HallucinationDetector(threshold=hallucination_threshold)
        self._pii = PIIDetector(threshold=pii_threshold)
        self._tox = ToxicityDetector(threshold=toxicity_threshold)
        self._qual = QualityDetector(threshold=quality_threshold)
        self._topic = TopicGuard(
            allowed_keywords=topic_allowed,
            blocked_keywords=topic_blocked,
            threshold=topic_threshold,
        )
        self.block_on_critical = block_on_critical
        self._alert_hooks: List[Callable[[AlertEvent], None]] = []
        self._async_alert_hooks: List[Callable[[AlertEvent], Any]] = []
        self._watch_count = 0
        self._failure_count = 0

    def on_alert(self, callback: Callable[[AlertEvent], None]) -> None:
        """Register a sync alert callback."""
        self._alert_hooks.append(callback)

    def on_alert_async(self, callback: Callable[[AlertEvent], Any]) -> None:
        """Register an async alert callback."""
        self._async_alert_hooks.append(callback)

    def watch(self, prompt: str, response: str, metadata: Optional[Dict[str, Any]] = None) -> WatchResult:
        """
        Synchronously watch a prompt/response pair.

        Args:
            prompt: The original prompt sent to the LLM.
            response: The LLM response to evaluate.
            metadata: Optional extra metadata for alert events.

        Returns:
            WatchResult with all detection scores.
        """
        t0 = time.monotonic()
        self._watch_count += 1
        metadata = metadata or {}

        detections: List[DetectionResult] = [
            self._hall.detect(prompt, response),
            self._pii.detect(prompt, response),
            self._tox.detect(prompt, response),
            self._qual.detect(prompt, response),
            self._topic.detect(prompt, response),
        ]

        detected_failures = [d for d in detections if d.detected]
        alerts_fired: List[str] = []

        for d in detected_failures:
            self._failure_count += 1
            event = AlertEvent(
                alert_id=f"alert-{self._watch_count}-{d.failure_type.value}",
                failure_type=d.failure_type,
                risk_level=d.risk_level,
                score=d.score,
                prompt=prompt,
                response=response,
                metadata=metadata,
            )
            alerts_fired.append(event.alert_id)
            self._fire_alerts(event)

        all_risks = [d.risk_level for d in detections]
        overall_risk = _max_risk(all_risks)
        overall_score = max(d.score for d in detections) if detections else 0.0
        passed = len(detected_failures) == 0

        latency_ms = (time.monotonic() - t0) * 1000
        result = WatchResult(
            prompt=prompt,
            response=response,
            passed=passed,
            overall_risk=overall_risk,
            overall_score=round(overall_score, 4),
            detections=detections,
            alerts_fired=alerts_fired,
            latency_ms=round(latency_ms, 2),
        )
        logger.info(
            "watch result passed=%s risk=%s score=%.3f latency_ms=%.1f",
            passed, overall_risk.value, overall_score, latency_ms,
        )
        return result

    async def awatch(self, prompt: str, response: str, metadata: Optional[Dict[str, Any]] = None) -> WatchResult:
        """Async watch — runs detectors in thread pool to avoid blocking."""
        loop = asyncio.get_event_loop()
        result = await loop.run_in_executor(None, lambda: self.watch(prompt, response, metadata))
        # fire async hooks
        for hook in self._async_alert_hooks:
            for alert_id in result.alerts_fired:
                event = AlertEvent(
                    alert_id=alert_id,
                    failure_type=FailureType.HALLUCINATION,  # placeholder
                    risk_level=result.overall_risk,
                    score=result.overall_score,
                    prompt=prompt,
                    response=response,
                    metadata=metadata or {},
                )
                try:
                    await hook(event)
                except Exception as exc:
                    logger.error("Async alert hook error: %s", exc)
        return result

    def _fire_alerts(self, event: AlertEvent) -> None:
        """Fire all registered sync alert hooks."""
        for hook in self._alert_hooks:
            try:
                hook(event)
            except Exception as exc:
                logger.error("Alert hook error: %s", exc)
                raise AlertDeliveryError(str(exc)) from exc

    def stats(self) -> Dict[str, Any]:
        """Return monitoring statistics."""
        return {
            "total_watched": self._watch_count,
            "total_failures": self._failure_count,
            "failure_rate": round(self._failure_count / max(self._watch_count, 1), 4),
        }
