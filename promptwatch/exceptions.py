"""Custom exceptions for promptwatch."""


class PromptWatchError(Exception):
    """Base exception for promptwatch."""


class HallucinationDetectedError(PromptWatchError):
    """Raised when hallucination risk exceeds threshold."""


class PIILeakDetectedError(PromptWatchError):
    """Raised when PII is found in LLM output."""


class TopicDriftError(PromptWatchError):
    """Raised when output topic drifts from expected domain."""


class SemanticDriftError(PromptWatchError):
    """Raised when semantic shift exceeds threshold."""


class BudgetExceededError(PromptWatchError):
    """Raised when monitoring budget is exceeded."""


class AlertDeliveryError(PromptWatchError):
    """Raised when an alert callback fails."""
