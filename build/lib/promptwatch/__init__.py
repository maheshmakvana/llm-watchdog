"""
promptwatch — Production-grade silent failure detection for LLM applications.

Detects hallucinations, PII leaks, topic drift, toxicity, and quality degradation
in real time with zero traditional APM dependency.
"""
from .watcher import PromptWatcher
from .models import (
    WatchResult,
    DetectionResult,
    AlertEvent,
    DriftSnapshot,
    RiskLevel,
    FailureType,
)
from .exceptions import (
    PromptWatchError,
    HallucinationDetectedError,
    PIILeakDetectedError,
    TopicDriftError,
    SemanticDriftError,
    BudgetExceededError,
    AlertDeliveryError,
)
from .metrics import (
    HallucinationDetector,
    PIIDetector,
    TopicGuard,
    ToxicityDetector,
    QualityDetector,
)
from .advanced import (
    WatchCache,
    WatchPipeline,
    WatchValidator,
    ConfidenceScorer,
    RateLimiter,
    batch_watch,
    abatch_watch,
    OperationProfiler,
    DriftDetector,
    StreamingWatcher,
    WatchDiff,
    RegressionTracker,
    AgentWatchSession,
    PIIScrubber,
    AuditLog,
    CostLedger,
)

__version__ = "1.0.0"
__all__ = [
    # Core
    "PromptWatcher",
    # Models
    "WatchResult", "DetectionResult", "AlertEvent", "DriftSnapshot",
    "RiskLevel", "FailureType",
    # Exceptions
    "PromptWatchError", "HallucinationDetectedError", "PIILeakDetectedError",
    "TopicDriftError", "SemanticDriftError", "BudgetExceededError", "AlertDeliveryError",
    # Detectors
    "HallucinationDetector", "PIIDetector", "TopicGuard", "ToxicityDetector", "QualityDetector",
    # Advanced
    "WatchCache", "WatchPipeline", "WatchValidator", "ConfidenceScorer",
    "RateLimiter", "batch_watch", "abatch_watch",
    "OperationProfiler", "DriftDetector",
    "StreamingWatcher",
    "WatchDiff", "RegressionTracker",
    "AgentWatchSession",
    "PIIScrubber", "AuditLog",
    "CostLedger",
]
