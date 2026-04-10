"""Custom exceptions for llm_watchdog."""


class LlmWatchdogError(Exception):
    """Base exception for llm-watchdog."""


class HallucinationDetectedError(LlmWatchdogError):
    """Raised when hallucination risk exceeds threshold."""


class PIILeakDetectedError(LlmWatchdogError):
    """Raised when PII is found in LLM output."""


class TopicDriftError(LlmWatchdogError):
    """Raised when output topic drifts from expected domain."""


class SemanticDriftError(LlmWatchdogError):
    """Raised when semantic shift exceeds threshold."""


class BudgetExceededError(LlmWatchdogError):
    """Raised when monitoring budget is exceeded."""


class AlertDeliveryError(LlmWatchdogError):
    """Raised when an alert callback fails."""
