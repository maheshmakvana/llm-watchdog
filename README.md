# llm-watchdog

**Production-grade silent failure detection for LLM applications.**

Traditional monitoring (Datadog, New Relic) shows 200 OK in 1.2 seconds — but it cannot detect hallucinations, PII leaks, topic drift, or quality degradation in your LLM responses. `llm-watchdog` fills that gap.

```bash
pip install llm-watchdog
```

---

## Why llm-watchdog?

| Problem | Traditional APM | llm-watchdog |
|---------|----------------|-------------|
| Hallucination risk | Blind | Scored 0–1 |
| PII leaks in output | Blind | Detected + alerted |
| Topic drift | Blind | Keyword + coverage guard |
| Toxicity | Blind | Pattern-matched |
| Quality degradation | Blind | Refusal + repetition check |
| Semantic drift over time | Blind | PSI-based drift detector |

---

## Quickstart

```python
from llm_watchdog import LlmWatchdog

watcher = LlmWatchdog()

result = watcher.watch(
    prompt="What is the capital of France?",
    response="The capital of France is Paris.",
)

print(result.passed)          # True
print(result.overall_score)   # 0.0
print(result.overall_risk)    # RiskLevel.LOW
```

---

## Alert Hooks

```python
from llm_watchdog import LlmWatchdog, AlertEvent

watcher = LlmWatchdog(pii_threshold=0.1)

def my_alert(event: AlertEvent):
    print(f"ALERT: {event.failure_type.value} — score={event.score:.2f}")

watcher.on_alert(my_alert)
watcher.watch("Tell me about John", "Contact john@example.com at 555-555-5555")
# ALERT: pii_leak — score=0.40
```

---

## Async Support

```python
import asyncio
from llm_watchdog import LlmWatchdog

watcher = LlmWatchdog()

async def main():
    result = await watcher.awatch("prompt", "response")
    print(result.overall_risk)

asyncio.run(main())
```

---

## Batch Watching

```python
from llm_watchdog import LlmWatchdog, batch_watch, abatch_watch
import asyncio

watcher = LlmWatchdog()
pairs = [("prompt1", "response1"), ("prompt2", "response2")]

# Sync batch
results = batch_watch(watcher, pairs, max_workers=8)

# Async batch
results = asyncio.run(abatch_watch(watcher, pairs, concurrency=8))
```

---

## Topic Guard

```python
from llm_watchdog import LlmWatchdog

watcher = LlmWatchdog(
    topic_allowed=["python", "code", "programming", "function"],
    topic_blocked=["politics", "religion", "violence"],
)
result = watcher.watch("How do I code?", "This involves violent politics.")
# topic drift detected
```

---

## Advanced Features

### Caching
```python
from llm_watchdog import LlmWatchdog, WatchCache

watcher = LlmWatchdog()
cache = WatchCache(max_size=512, ttl=300)
cached_watch = cache.memoize(watcher)
result = cached_watch("prompt", "response")
print(cache.stats())
# {'hits': 0, 'misses': 1, 'hit_rate': 0.0, 'evictions': 0, 'size': 1}
```

### Pipeline
```python
from llm_watchdog import LlmWatchdog, WatchPipeline

watcher = LlmWatchdog()
result = watcher.watch("prompt", "response")

pipeline = WatchPipeline()
pipeline.add_step("log", lambda r: r)
pipeline.filter(lambda r: r.passed)
out = pipeline.run(result)
print(pipeline.audit())
```

### Validation
```python
from llm_watchdog import LlmWatchdog, WatchValidator, ConfidenceScorer

watcher = LlmWatchdog()
result = watcher.watch("prompt", "response")

validator = WatchValidator().require_pass().max_score(0.8)
violations = validator.validate(result)

scorer = ConfidenceScorer()
print(scorer.score(result))          # 0–1, higher = safer
print(scorer.field_scores(result))   # per-detector breakdown
```

### Drift Detection
```python
from llm_watchdog import DriftDetector

detector = DriftDetector(threshold=0.1)
detector.set_baseline([0.1, 0.2, 0.1, 0.15])
print(detector.is_drifting([0.5, 0.6, 0.4, 0.55]))  # True
print(detector.psi([0.5, 0.6, 0.4, 0.55]))           # PSI value
```

### Streaming
```python
from llm_watchdog import LlmWatchdog, StreamingWatcher

watcher = LlmWatchdog()
sw = StreamingWatcher(watcher)

pairs = [("prompt1", "response1"), ("prompt2", "response2")]
for result in sw.stream(pairs):
    print(result.overall_risk)
```

### Diff & Regression Tracking
```python
from llm_watchdog import LlmWatchdog, WatchDiff, RegressionTracker

watcher = LlmWatchdog()
r1 = watcher.watch("prompt", "safe response")
r2 = watcher.watch("prompt", "Contact john@example.com")

diff = WatchDiff(before=r1, after=r2)
print(diff.score_delta)        # +0.2
print(diff.new_failures)       # ['pii_leak']
print(diff.to_json())

tracker = RegressionTracker(tolerance=0.05)
tracker.record("deploy_v1", 0.10)
tracker.record("deploy_v2", 0.25)
print(tracker.is_regressing())  # True
print(tracker.summary())
```

### Agent Session Monitoring
```python
from llm_watchdog import LlmWatchdog, AgentWatchSession

watcher = LlmWatchdog()
session = AgentWatchSession(watcher, max_risk_budget=2.0)

for prompt, response in agent_turns:
    session.watch_turn(prompt, response)
    if session.is_over_budget():
        raise RuntimeError("Agent risk budget exceeded")

print(session.session_summary())
```

### PII Scrubbing
```python
from llm_watchdog import PIIScrubber

scrubber = PIIScrubber()
clean = scrubber.mask("Email me at alice@example.com or call 555-123-4567")
# "Email me at [REDACTED_EMAIL] or call [REDACTED_PHONE]"
```

### Audit Log
```python
from llm_watchdog import LlmWatchdog, AuditLog

watcher = LlmWatchdog()
audit = AuditLog()

result = watcher.watch("prompt", "response")
audit.record(result)
audit.export_audit("audit.json")
print(audit.entries())
```

### Cost Ledger
```python
from llm_watchdog import CostLedger

ledger = CostLedger(cost_per_watch=0.0001)
ledger.record("default", count=100)
ledger.record("batch", count=500)
print(ledger.total_cost())
print(ledger.report())
```

### Rate Limiter
```python
from llm_watchdog import LlmWatchdog, RateLimiter
import asyncio

rl = RateLimiter(rate=10, capacity=10)  # 10 calls/sec

# Sync
rl.acquire()

# Async
async def main():
    await rl.async_acquire()

asyncio.run(main())
```

### FastAPI Middleware
```python
from fastapi import FastAPI
from llm_watchdog import LlmWatchdog
from llm_watchdog.middleware import create_fastapi_middleware

app = FastAPI()
watcher = LlmWatchdog()
app.add_middleware(create_fastapi_middleware(watcher))
```

### Flask Middleware
```python
from flask import Flask
from llm_watchdog import LlmWatchdog
from llm_watchdog.middleware import create_flask_middleware

app = Flask(__name__)
watcher = LlmWatchdog()
create_flask_middleware(app, watcher)
```

---

## CLI

```bash
llm-watchdog --prompt "What is the capital?" --response "Paris is the capital."
llm-watchdog --prompt "Tell me about John" --response "Call 555-123-4567" --json
```

---

## Configuration

| Parameter | Default | Description |
|-----------|---------|-------------|
| `hallucination_threshold` | 0.5 | Flag score above this |
| `pii_threshold` | 0.1 | Any PII triggers flag |
| `toxicity_threshold` | 0.3 | Toxic content threshold |
| `quality_threshold` | 0.4 | Low-quality response threshold |
| `topic_allowed` | None | Keywords expected in response |
| `topic_blocked` | None | Keywords that always trigger flag |
| `block_on_critical` | False | Raise exception on CRITICAL risk |

---

## All Exports

```python
from llm_watchdog import (
    # Core
    LlmWatchdog,
    # Models
    WatchResult, DetectionResult, AlertEvent, DriftSnapshot, RiskLevel, FailureType,
    # Exceptions
    LlmWatchdogError, HallucinationDetectedError, PIILeakDetectedError,
    TopicDriftError, SemanticDriftError, BudgetExceededError, AlertDeliveryError,
    # Detectors
    HallucinationDetector, PIIDetector, TopicGuard, ToxicityDetector, QualityDetector,
    # Advanced
    WatchCache, WatchPipeline, WatchValidator, ConfidenceScorer,
    RateLimiter, batch_watch, abatch_watch,
    OperationProfiler, DriftDetector, StreamingWatcher,
    WatchDiff, RegressionTracker, AgentWatchSession,
    PIIScrubber, AuditLog, CostLedger,
)
```

---

## Installation

```bash
pip install llm-watchdog                    # core only
pip install llm-watchdog[fastapi]           # with FastAPI middleware
pip install llm-watchdog[flask]             # with Flask middleware
pip install llm-watchdog[opentelemetry]     # with OTEL tracing
pip install llm-watchdog[all]               # everything
```

---

## Keywords

llm monitoring, ai observability, hallucination detection, pii detection, semantic drift, production ai monitoring, llm alerts, ai safety, prompt monitoring, silent failure detection, llm quality, topic drift, ai reliability, llm guardrails, prompt injection, ai production
