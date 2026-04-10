"""
Advanced features for promptwatch.

Categories covered:
  1 - Caching & Semantic Deduplication  (WatchCache)
  2 - Pipeline / Fluent API             (WatchPipeline)
  3 - Validation & Guardrails           (WatchValidator, ConfidenceScorer)
  4 - Async & Concurrency               (RateLimiter, batch_watch, abatch_watch)
  5 - Observability & Tracing           (OperationProfiler, DriftDetector)
  6 - Streaming                         (StreamingWatcher)
  7 - Diff & Regression                 (WatchDiff, RegressionTracker)
  8 - Agentic / LLM-Native              (AgentWatchSession)
  9 - Security & PII                    (AuditLog, PIIScrubber)
  10 - Cost Optimization                (CostLedger)
"""
from __future__ import annotations

import asyncio
import gzip
import hashlib
import json
import logging
import math
import pickle
import re
import threading
import time
import uuid
from collections import deque
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Callable, Dict, Generator, List, Optional, Tuple

from .models import WatchResult, RiskLevel, FailureType
from .watcher import PromptWatcher

logger = logging.getLogger(__name__)


# ── Category 1: Caching ────────────────────────────────────────────────────

class WatchCache:
    """Thread-safe LRU cache for WatchResult with TTL and SHA-256 keying."""

    def __init__(self, max_size: int = 512, ttl: float = 300.0) -> None:
        self.max_size = max_size
        self.ttl = ttl
        self._lock = threading.Lock()
        self._store: Dict[str, Tuple[WatchResult, float]] = {}
        self._order: deque = deque()
        self._hits = 0
        self._misses = 0
        self._evictions = 0

    @staticmethod
    def _key(prompt: str, response: str) -> str:
        return hashlib.sha256(f"{prompt}|||{response}".encode()).hexdigest()

    def get(self, prompt: str, response: str) -> Optional[WatchResult]:
        key = self._key(prompt, response)
        with self._lock:
            if key in self._store:
                result, ts = self._store[key]
                if time.monotonic() - ts < self.ttl:
                    self._hits += 1
                    return result
                del self._store[key]
            self._misses += 1
            return None

    def put(self, prompt: str, response: str, result: WatchResult) -> None:
        key = self._key(prompt, response)
        with self._lock:
            if key in self._store:
                self._order.remove(key)
            elif len(self._store) >= self.max_size:
                oldest = self._order.popleft()
                del self._store[oldest]
                self._evictions += 1
            self._store[key] = (result, time.monotonic())
            self._order.append(key)

    def memoize(self, watcher: PromptWatcher) -> Callable:
        """Wrap PromptWatcher.watch with cache."""
        def cached_watch(prompt: str, response: str, **kwargs) -> WatchResult:
            hit = self.get(prompt, response)
            if hit is not None:
                return hit
            result = watcher.watch(prompt, response, **kwargs)
            self.put(prompt, response, result)
            return result
        return cached_watch

    def stats(self) -> Dict[str, Any]:
        total = self._hits + self._misses
        return {
            "hits": self._hits,
            "misses": self._misses,
            "hit_rate": round(self._hits / max(total, 1), 4),
            "evictions": self._evictions,
            "size": len(self._store),
        }

    def save(self, path: str) -> None:
        with self._lock:
            with open(path, "wb") as f:
                pickle.dump({"store": self._store, "order": list(self._order)}, f)

    def load(self, path: str) -> None:
        with open(path, "rb") as f:
            data = pickle.load(f)
        with self._lock:
            self._store = data["store"]
            self._order = deque(data["order"])


# ── Category 2: Pipeline ──────────────────────────────────────────────────

@dataclass
class _PipelineStep:
    name: str
    fn: Callable
    duration_ms: float = 0.0


class WatchPipeline:
    """Fluent chainable pipeline for LLM watch post-processing."""

    def __init__(self) -> None:
        self._steps: List[_PipelineStep] = []
        self._audit_log: List[Dict[str, Any]] = []

    def add_step(self, name: str, fn: Callable[[WatchResult], WatchResult]) -> "WatchPipeline":
        self._steps.append(_PipelineStep(name=name, fn=fn))
        return self

    def filter(self, predicate: Callable[[WatchResult], bool], name: str = "filter") -> "WatchPipeline":
        def _filter(r: WatchResult) -> WatchResult:
            if not predicate(r):
                raise StopIteration("filtered out")
            return r
        self._steps.append(_PipelineStep(name=name, fn=_filter))
        return self

    def run(self, result: WatchResult) -> Optional[WatchResult]:
        current = result
        for step in self._steps:
            t0 = time.monotonic()
            try:
                current = step.fn(current)
            except StopIteration:
                return None
            step.duration_ms = (time.monotonic() - t0) * 1000
            self._audit_log.append({
                "step": step.name,
                "duration_ms": round(step.duration_ms, 3),
                "risk": current.overall_risk.value if current else None,
            })
        return current

    async def arun(self, result: WatchResult) -> Optional[WatchResult]:
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(None, lambda: self.run(result))

    def audit(self) -> List[Dict[str, Any]]:
        return list(self._audit_log)

    def with_retry(self, n: int = 3, backoff: float = 2.0) -> "WatchPipeline":
        """Wrap last added step with retry logic."""
        if not self._steps:
            raise ValueError("No steps to wrap with retry.")
        step = self._steps[-1]
        original_fn = step.fn

        def _retry_fn(r: WatchResult) -> WatchResult:
            last_exc: Optional[Exception] = None
            for attempt in range(n):
                try:
                    return original_fn(r)
                except Exception as exc:
                    last_exc = exc
                    time.sleep(backoff ** attempt)
            raise RuntimeError(f"Step '{step.name}' failed after {n} retries") from last_exc

        step.fn = _retry_fn
        return self


# ── Category 3: Validation & Guardrails ───────────────────────────────────

@dataclass
class WatchRule:
    """A single declarative validation rule for WatchResults."""
    name: str
    check: Callable[[WatchResult], bool]
    message: str = ""


class WatchValidator:
    """Declarative rule-based validator for WatchResults."""

    def __init__(self) -> None:
        self._rules: List[WatchRule] = []

    def add_rule(self, name: str, check: Callable[[WatchResult], bool], message: str = "") -> "WatchValidator":
        self._rules.append(WatchRule(name=name, check=check, message=message))
        return self

    def require_pass(self) -> "WatchValidator":
        return self.add_rule("must_pass", lambda r: r.passed, "Watch result must pass all detectors")

    def max_score(self, threshold: float) -> "WatchValidator":
        return self.add_rule(f"max_score_{threshold}", lambda r: r.overall_score <= threshold, f"Score must be <= {threshold}")

    def validate(self, result: WatchResult) -> List[str]:
        """Return list of rule violation messages (empty = valid)."""
        violations: List[str] = []
        for rule in self._rules:
            try:
                if not rule.check(result):
                    violations.append(rule.message or rule.name)
            except Exception as exc:
                violations.append(f"Rule '{rule.name}' error: {exc}")
        return violations


class ConfidenceScorer:
    """Compute an aggregate confidence score for a WatchResult."""

    def score(self, result: WatchResult) -> float:
        """Return confidence that the response is safe (1.0 = fully safe)."""
        return round(1.0 - result.overall_score, 4)

    def field_scores(self, result: WatchResult) -> Dict[str, float]:
        """Per-detector confidence scores."""
        return {d.failure_type.value: round(1.0 - d.score, 4) for d in result.detections}


# ── Category 4: Async & Concurrency ──────────────────────────────────────

class RateLimiter:
    """Token-bucket rate limiter — sync and async."""

    def __init__(self, rate: float, capacity: float) -> None:
        self.rate = rate
        self.capacity = capacity
        self._tokens = capacity
        self._last = time.monotonic()
        self._lock = threading.Lock()

    def _refill(self) -> None:
        now = time.monotonic()
        elapsed = now - self._last
        self._tokens = min(self.capacity, self._tokens + elapsed * self.rate)
        self._last = now

    def acquire(self, tokens: float = 1.0) -> None:
        with self._lock:
            self._refill()
            if self._tokens < tokens:
                deficit = tokens - self._tokens
                time.sleep(deficit / self.rate)
                self._refill()
            self._tokens -= tokens

    async def async_acquire(self, tokens: float = 1.0) -> None:
        loop = asyncio.get_event_loop()
        await loop.run_in_executor(None, lambda: self.acquire(tokens))


def batch_watch(
    watcher: PromptWatcher,
    pairs: List[Tuple[str, str]],
    max_workers: int = 8,
) -> List[WatchResult]:
    """Concurrent sync batch watch using ThreadPoolExecutor."""
    with ThreadPoolExecutor(max_workers=max_workers) as pool:
        futures = [pool.submit(watcher.watch, p, r) for p, r in pairs]
        return [f.result() for f in futures]


async def abatch_watch(
    watcher: PromptWatcher,
    pairs: List[Tuple[str, str]],
    concurrency: int = 8,
) -> List[WatchResult]:
    """Async concurrent batch watch."""
    sem = asyncio.Semaphore(concurrency)

    async def _one(p: str, r: str) -> WatchResult:
        async with sem:
            return await watcher.awatch(p, r)

    return await asyncio.gather(*[_one(p, r) for p, r in pairs])


# ── Category 5: Observability & Tracing ──────────────────────────────────

class OperationProfiler:
    """Context-manager and decorator for timing watch operations."""

    def __init__(self, name: str = "operation") -> None:
        self.name = name
        self._start: float = 0.0
        self.duration_ms: float = 0.0
        self._records: List[Dict[str, Any]] = []

    def __enter__(self) -> "OperationProfiler":
        self._start = time.monotonic()
        return self

    def __exit__(self, *args: Any) -> None:
        self.duration_ms = (time.monotonic() - self._start) * 1000
        self._records.append({"name": self.name, "duration_ms": round(self.duration_ms, 3), "ts": time.time()})
        logger.debug("ProfiledOp[%s] %.1f ms", self.name, self.duration_ms)

    def records(self) -> List[Dict[str, Any]]:
        return list(self._records)


class DriftDetector:
    """Detects statistical drift in watch metric distributions using PSI."""

    def __init__(self, threshold: float = 0.1) -> None:
        self.threshold = threshold
        self._baseline: Optional[List[float]] = None

    def set_baseline(self, scores: List[float]) -> None:
        self._baseline = list(scores)

    def _psi(self, expected: List[float], actual: List[float]) -> float:
        """Population Stability Index."""
        n_bins = 10
        min_v = min(min(expected), min(actual))
        max_v = max(max(expected), max(actual)) + 1e-9
        bins = [min_v + i * (max_v - min_v) / n_bins for i in range(n_bins + 1)]

        def _hist(data: List[float]) -> List[float]:
            counts = [0] * n_bins
            for v in data:
                idx = min(int((v - min_v) / (max_v - min_v) * n_bins), n_bins - 1)
                counts[idx] += 1
            total = max(sum(counts), 1)
            return [max(c / total, 1e-4) for c in counts]

        exp_h = _hist(expected)
        act_h = _hist(actual)
        return sum((a - e) * math.log(a / e) for a, e in zip(act_h, exp_h))

    def is_drifting(self, current_scores: List[float]) -> bool:
        if self._baseline is None:
            return False
        psi = self._psi(self._baseline, current_scores)
        logger.debug("PSI=%.4f threshold=%.4f", psi, self.threshold)
        return psi > self.threshold

    def psi(self, current_scores: List[float]) -> float:
        if self._baseline is None:
            return 0.0
        return round(self._psi(self._baseline, current_scores), 6)


# ── Category 6: Streaming ────────────────────────────────────────────────

class StreamingWatcher:
    """Yield WatchResults one at a time from a large batch without buffering."""

    def __init__(self, watcher: PromptWatcher) -> None:
        self._watcher = watcher

    def stream(
        self, pairs: List[Tuple[str, str]]
    ) -> Generator[WatchResult, None, None]:
        """Stream watch results lazily."""
        for prompt, response in pairs:
            yield self._watcher.watch(prompt, response)

    async def astream(
        self, pairs: List[Tuple[str, str]]
    ):
        """Async stream watch results."""
        for prompt, response in pairs:
            result = await self._watcher.awatch(prompt, response)
            yield result


# ── Category 7: Diff & Regression ─────────────────────────────────────────

@dataclass
class WatchDiff:
    """Diff between two WatchResults."""
    before: WatchResult
    after: WatchResult

    @property
    def score_delta(self) -> float:
        return round(self.after.overall_score - self.before.overall_score, 4)

    @property
    def risk_changed(self) -> bool:
        return self.before.overall_risk != self.after.overall_risk

    @property
    def new_failures(self) -> List[str]:
        before_failures = {d.failure_type.value for d in self.before.detections if d.detected}
        after_failures = {d.failure_type.value for d in self.after.detections if d.detected}
        return list(after_failures - before_failures)

    @property
    def resolved_failures(self) -> List[str]:
        before_failures = {d.failure_type.value for d in self.before.detections if d.detected}
        after_failures = {d.failure_type.value for d in self.after.detections if d.detected}
        return list(before_failures - after_failures)

    def summary(self) -> str:
        return (
            f"Score delta: {self.score_delta:+.4f} | "
            f"Risk: {self.before.overall_risk.value} → {self.after.overall_risk.value} | "
            f"New failures: {self.new_failures} | Resolved: {self.resolved_failures}"
        )

    def to_json(self) -> Dict[str, Any]:
        return {
            "score_delta": self.score_delta,
            "before_risk": self.before.overall_risk.value,
            "after_risk": self.after.overall_risk.value,
            "new_failures": self.new_failures,
            "resolved_failures": self.resolved_failures,
        }


class RegressionTracker:
    """Track watch score history and detect regressions."""

    def __init__(self, tolerance: float = 0.05) -> None:
        self.tolerance = tolerance
        self._runs: List[Dict[str, Any]] = []

    def record(self, name: str, score: float) -> None:
        self._runs.append({"name": name, "score": score, "ts": time.time()})

    def is_regressing(self) -> bool:
        if len(self._runs) < 2:
            return False
        latest = self._runs[-1]["score"]
        baseline = self._runs[0]["score"]
        return latest > baseline + self.tolerance

    def history(self, n: int = 10) -> List[Dict[str, Any]]:
        return self._runs[-n:]

    def summary(self) -> str:
        if not self._runs:
            return "No runs recorded."
        best = min(r["score"] for r in self._runs)
        latest = self._runs[-1]["score"]
        return f"Runs: {len(self._runs)} | Best score: {best:.4f} | Latest: {latest:.4f} | Regressing: {self.is_regressing()}"


# ── Category 8: Agentic / LLM-Native ─────────────────────────────────────

class AgentWatchSession:
    """
    Multi-turn agent session monitor.
    Tracks cumulative risk across all turns and detects escalating failures.
    """

    def __init__(self, watcher: PromptWatcher, max_risk_budget: float = 2.0) -> None:
        self._watcher = watcher
        self.max_risk_budget = max_risk_budget
        self._turns: List[WatchResult] = []
        self._risk_budget_used = 0.0

    def watch_turn(self, prompt: str, response: str) -> WatchResult:
        result = self._watcher.watch(prompt, response)
        self._turns.append(result)
        self._risk_budget_used += result.overall_score
        return result

    def is_over_budget(self) -> bool:
        return self._risk_budget_used >= self.max_risk_budget

    def session_summary(self) -> Dict[str, Any]:
        return {
            "turns": len(self._turns),
            "risk_budget_used": round(self._risk_budget_used, 4),
            "over_budget": self.is_over_budget(),
            "avg_score": round(sum(r.overall_score for r in self._turns) / max(len(self._turns), 1), 4),
            "failures": sum(1 for r in self._turns if not r.passed),
        }


# ── Category 9: Security & PII ────────────────────────────────────────────

_PII_REDACT_PATTERNS = {
    "email": (re.compile(r"\b[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}\b"), "[REDACTED_EMAIL]"),
    "phone": (re.compile(r"\b(\+1[\s\-]?)?\(?\d{3}\)?[\s\-]?\d{3}[\s\-]?\d{4}\b"), "[REDACTED_PHONE]"),
    "ssn": (re.compile(r"\b\d{3}[-\s]?\d{2}[-\s]?\d{4}\b"), "[REDACTED_SSN]"),
    "credit_card": (re.compile(r"\b(?:\d{4}[\s\-]?){3}\d{4}\b"), "[REDACTED_CC]"),
    "ip": (re.compile(r"\b(?:\d{1,3}\.){3}\d{1,3}\b"), "[REDACTED_IP]"),
}


class PIIScrubber:
    """Scrub PII from text before logging or persistence."""

    def mask(self, text: str) -> str:
        for name, (pattern, replacement) in _PII_REDACT_PATTERNS.items():
            text = pattern.sub(replacement, text)
        return text


class AuditLog:
    """Immutable append-only audit log for all watch events."""

    def __init__(self) -> None:
        self._log: List[Dict[str, Any]] = []
        self._lock = threading.Lock()

    def record(self, result: WatchResult) -> None:
        entry = {
            "id": str(uuid.uuid4()),
            "ts": datetime.utcnow().isoformat(),
            "passed": result.passed,
            "risk": result.overall_risk.value,
            "score": result.overall_score,
            "failures": [d.failure_type.value for d in result.detections if d.detected],
        }
        with self._lock:
            self._log.append(entry)

    def export_audit(self, path: str) -> None:
        with self._lock:
            with open(path, "w") as f:
                json.dump(self._log, f, indent=2)

    def entries(self) -> List[Dict[str, Any]]:
        with self._lock:
            return list(self._log)


# ── Category 10: Cost Optimization ───────────────────────────────────────

class CostLedger:
    """Track cost per watch call and report totals."""

    def __init__(self, cost_per_watch: float = 0.0001) -> None:
        self.cost_per_watch = cost_per_watch
        self._records: List[Dict[str, Any]] = []
        self._lock = threading.Lock()

    def record(self, route: str, count: int = 1) -> None:
        cost = count * self.cost_per_watch
        with self._lock:
            self._records.append({"route": route, "count": count, "cost": cost, "ts": time.time()})

    def total_cost(self) -> float:
        with self._lock:
            return round(sum(r["cost"] for r in self._records), 6)

    def report(self) -> Dict[str, Any]:
        with self._lock:
            by_route: Dict[str, float] = {}
            for r in self._records:
                by_route[r["route"]] = by_route.get(r["route"], 0.0) + r["cost"]
            return {"total": self.total_cost(), "by_route": by_route, "calls": len(self._records)}
