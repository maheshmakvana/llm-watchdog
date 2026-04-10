"""Tests for llm_watchdog core and advanced features."""
from __future__ import annotations

import asyncio
import pytest

from llm_watchdog import (
    LlmWatchdog, WatchResult, RiskLevel, FailureType,
    HallucinationDetector, PIIDetector, TopicGuard, ToxicityDetector, QualityDetector,
)
from llm_watchdog.advanced import (
    WatchCache, WatchPipeline, WatchValidator, ConfidenceScorer,
    RateLimiter, batch_watch, abatch_watch,
    OperationProfiler, DriftDetector,
    StreamingWatcher, WatchDiff, RegressionTracker,
    AgentWatchSession, PIIScrubber, AuditLog, CostLedger,
)


SAFE_PROMPT = "What is the capital of France?"
SAFE_RESPONSE = "The capital of France is Paris."
PII_RESPONSE = "Contact john.doe@example.com or call 555-123-4567."
HALLUCINATION_RESPONSE = "I think, probably, studies show that Paris might be the most populated city."
TOXIC_RESPONSE = "You should kill yourself."


# ── Core ──────────────────────────────────────────────────────────────────

def test_watch_safe_response():
    watcher = LlmWatchdog()
    result = watcher.watch(SAFE_PROMPT, SAFE_RESPONSE)
    assert isinstance(result, WatchResult)
    assert result.passed is True
    assert result.overall_score >= 0.0


def test_watch_pii_detected():
    watcher = LlmWatchdog(pii_threshold=0.1)
    result = watcher.watch(SAFE_PROMPT, PII_RESPONSE)
    pii = next(d for d in result.detections if d.failure_type == FailureType.PII_LEAK)
    assert pii.detected is True
    assert pii.score > 0


def test_watch_toxicity_detected():
    watcher = LlmWatchdog(toxicity_threshold=0.3)
    result = watcher.watch(SAFE_PROMPT, TOXIC_RESPONSE)
    tox = next(d for d in result.detections if d.failure_type == FailureType.TOXICITY)
    assert tox.detected is True


def test_watch_hallucination_detected():
    watcher = LlmWatchdog(hallucination_threshold=0.3)
    result = watcher.watch(SAFE_PROMPT, HALLUCINATION_RESPONSE)
    hall = next(d for d in result.detections if d.failure_type == FailureType.HALLUCINATION)
    assert hall.score > 0


def test_watch_alert_fired():
    fired = []
    watcher = LlmWatchdog(pii_threshold=0.1)
    watcher.on_alert(lambda e: fired.append(e))
    watcher.watch(SAFE_PROMPT, PII_RESPONSE)
    assert len(fired) > 0


def test_watch_stats():
    watcher = LlmWatchdog()
    watcher.watch(SAFE_PROMPT, SAFE_RESPONSE)
    s = watcher.stats()
    assert s["total_watched"] == 1


def test_watch_result_to_dict():
    watcher = LlmWatchdog()
    result = watcher.watch(SAFE_PROMPT, SAFE_RESPONSE)
    d = result.to_dict()
    assert "passed" in d
    assert "overall_score" in d


def test_async_watch():
    watcher = LlmWatchdog()
    result = asyncio.run(watcher.awatch(SAFE_PROMPT, SAFE_RESPONSE))
    assert isinstance(result, WatchResult)


# ── Detectors ─────────────────────────────────────────────────────────────

def test_hallucination_detector():
    det = HallucinationDetector(threshold=0.2)
    result = det.detect(SAFE_PROMPT, HALLUCINATION_RESPONSE)
    assert result.failure_type == FailureType.HALLUCINATION


def test_pii_detector_email():
    det = PIIDetector()
    result = det.detect("q", "Email me at test@example.com")
    assert result.detected is True
    assert "email" in result.details["pii_types_found"]


def test_topic_guard_blocked():
    guard = TopicGuard(blocked_keywords=["violence", "attack"])
    result = guard.detect("q", "This involves a violent attack.")
    assert result.detected is True


def test_quality_detector_empty():
    det = QualityDetector(threshold=0.4, min_length=20)
    result = det.detect("q", "ok")
    assert result.detected is True


# ── Advanced ──────────────────────────────────────────────────────────────

def test_watch_cache():
    watcher = LlmWatchdog()
    cache = WatchCache(max_size=10, ttl=60)
    cached = cache.memoize(watcher)
    r1 = cached(SAFE_PROMPT, SAFE_RESPONSE)
    r2 = cached(SAFE_PROMPT, SAFE_RESPONSE)
    assert r1.overall_score == r2.overall_score
    stats = cache.stats()
    assert stats["hits"] == 1


def test_watch_pipeline():
    watcher = LlmWatchdog()
    result = watcher.watch(SAFE_PROMPT, SAFE_RESPONSE)
    pipeline = WatchPipeline()
    pipeline.add_step("identity", lambda r: r)
    out = pipeline.run(result)
    assert out is not None
    assert len(pipeline.audit()) == 1


def test_watch_validator():
    watcher = LlmWatchdog()
    result = watcher.watch(SAFE_PROMPT, SAFE_RESPONSE)
    validator = WatchValidator().require_pass().max_score(0.99)
    violations = validator.validate(result)
    assert isinstance(violations, list)


def test_confidence_scorer():
    watcher = LlmWatchdog()
    result = watcher.watch(SAFE_PROMPT, SAFE_RESPONSE)
    scorer = ConfidenceScorer()
    score = scorer.score(result)
    assert 0.0 <= score <= 1.0
    fields = scorer.field_scores(result)
    assert len(fields) > 0


def test_rate_limiter_sync():
    rl = RateLimiter(rate=100, capacity=10)
    rl.acquire(1)


def test_batch_watch():
    watcher = LlmWatchdog()
    pairs = [(SAFE_PROMPT, SAFE_RESPONSE)] * 3
    results = batch_watch(watcher, pairs)
    assert len(results) == 3


def test_abatch_watch():
    watcher = LlmWatchdog()
    pairs = [(SAFE_PROMPT, SAFE_RESPONSE)] * 3
    results = asyncio.run(abatch_watch(watcher, pairs))
    assert len(results) == 3


def test_operation_profiler():
    with OperationProfiler("test_op") as prof:
        pass
    assert prof.duration_ms >= 0
    assert len(prof.records()) == 1


def test_drift_detector():
    det = DriftDetector(threshold=0.2)
    det.set_baseline([0.1, 0.2, 0.1, 0.15, 0.1])
    assert isinstance(det.is_drifting([0.1, 0.15, 0.1, 0.12, 0.1]), bool)


def test_streaming_watcher():
    watcher = LlmWatchdog()
    sw = StreamingWatcher(watcher)
    pairs = [(SAFE_PROMPT, SAFE_RESPONSE)] * 3
    results = list(sw.stream(pairs))
    assert len(results) == 3


def test_watch_diff():
    watcher = LlmWatchdog()
    r1 = watcher.watch(SAFE_PROMPT, SAFE_RESPONSE)
    r2 = watcher.watch(SAFE_PROMPT, PII_RESPONSE)
    diff = WatchDiff(before=r1, after=r2)
    assert isinstance(diff.summary(), str)
    d = diff.to_json()
    assert "score_delta" in d


def test_regression_tracker():
    rt = RegressionTracker(tolerance=0.05)
    rt.record("run1", 0.1)
    rt.record("run2", 0.3)
    assert rt.is_regressing() is True
    assert len(rt.history()) == 2


def test_agent_watch_session():
    watcher = LlmWatchdog()
    session = AgentWatchSession(watcher, max_risk_budget=10.0)
    session.watch_turn(SAFE_PROMPT, SAFE_RESPONSE)
    summary = session.session_summary()
    assert summary["turns"] == 1


def test_pii_scrubber():
    scrubber = PIIScrubber()
    masked = scrubber.mask("Email: test@example.com, SSN: 123-45-6789")
    assert "REDACTED" in masked
    assert "test@example.com" not in masked


def test_audit_log():
    watcher = LlmWatchdog()
    result = watcher.watch(SAFE_PROMPT, SAFE_RESPONSE)
    audit = AuditLog()
    audit.record(result)
    entries = audit.entries()
    assert len(entries) == 1
    assert "passed" in entries[0]


def test_cost_ledger():
    ledger = CostLedger(cost_per_watch=0.001)
    ledger.record("default", count=5)
    assert ledger.total_cost() == pytest.approx(0.005, rel=1e-4)
    report = ledger.report()
    assert report["calls"] == 1
