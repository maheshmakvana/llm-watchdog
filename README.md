# promptwatch

**Production-grade silent failure detection for LLM applications.**

Traditional monitoring (Datadog, New Relic) shows 200 OK in 1.2 seconds — but it cannot detect hallucinations, PII leaks, topic drift, or quality degradation in your LLM responses. `promptwatch` fills that gap.

```bash
pip install promptwatch
```

---

## Why promptwatch?

| Problem | Traditional APM | promptwatch |
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
from promptwatch import PromptWatcher

watcher = PromptWatcher()

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
from promptwatch import PromptWatcher, AlertEvent

watcher = PromptWatcher(pii_threshold=0.1)

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
from promptwatch import PromptWatcher

watcher = PromptWatcher()

async def main():
    result = await watcher.awatch("prompt", "response")
    print(result.overall_risk)

asyncio.run(main())
```

---

## Batch Watching

```python
from promptwatch.advanced import batch_watch, abatch_watch

pairs = [("prompt1", "response1"), ("prompt2", "response2")]
results = batch_watch(watcher, pairs, max_workers=8)
```

---

## Topic Guard

```python
watcher = PromptWatcher(
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
from promptwatch.advanced import WatchCache
cache = WatchCache(max_size=512, ttl=300)
cached_watch = cache.memoize(watcher)
result = cached_watch("prompt", "response")
print(cache.stats())
```

### Drift Detection
```python
from promptwatch.advanced import DriftDetector
detector = DriftDetector(threshold=0.1)
detector.set_baseline([0.1, 0.2, 0.1, 0.15])
print(detector.is_drifting([0.5, 0.6, 0.4, 0.55]))  # True
```

### Pipeline
```python
from promptwatch.advanced import WatchPipeline
pipeline = WatchPipeline()
pipeline.add_step("log", lambda r: r)
pipeline.filter(lambda r: r.passed)
result = pipeline.run(watch_result)
```

### PII Scrubbing
```python
from promptwatch.advanced import PIIScrubber
scrubber = PIIScrubber()
clean = scrubber.mask("Email me at alice@example.com or call 555-123-4567")
# "Email me at [REDACTED_EMAIL] or call [REDACTED_PHONE]"
```

### Regression Tracking
```python
from promptwatch.advanced import RegressionTracker
tracker = RegressionTracker(tolerance=0.05)
tracker.record("deploy_v1", 0.10)
tracker.record("deploy_v2", 0.25)
print(tracker.is_regressing())  # True
```

### Agent Session Monitoring
```python
from promptwatch.advanced import AgentWatchSession
session = AgentWatchSession(watcher, max_risk_budget=2.0)
for prompt, response in agent_turns:
    session.watch_turn(prompt, response)
    if session.is_over_budget():
        raise RuntimeError("Agent risk budget exceeded")
```

### FastAPI Middleware
```python
from fastapi import FastAPI
from promptwatch import PromptWatcher
from promptwatch.middleware import create_fastapi_middleware

app = FastAPI()
watcher = PromptWatcher()
app.add_middleware(create_fastapi_middleware(watcher))
```

---

## CLI

```bash
promptwatch --prompt "What is the capital?" --response "Paris is the capital."
promptwatch --prompt "Tell me about John" --response "Call 555-123-4567" --json
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

## Installation

```bash
pip install promptwatch                    # core only
pip install promptwatch[fastapi]           # with FastAPI middleware
pip install promptwatch[flask]             # with Flask middleware
pip install promptwatch[opentelemetry]     # with OTEL tracing
pip install promptwatch[all]               # everything
```

---

## Keywords

llm monitoring, ai observability, hallucination detection, pii detection, semantic drift, production ai monitoring, llm alerts, ai safety, prompt monitoring, silent failure detection, llm quality, topic drift, ai reliability, llm guardrails, prompt injection, ai production
