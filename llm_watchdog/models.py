"""Pydantic models for llm_watchdog data structures."""
from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field


class RiskLevel(str, Enum):
    """Risk severity levels."""
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class FailureType(str, Enum):
    """Types of production failures detected."""
    HALLUCINATION = "hallucination"
    PII_LEAK = "pii_leak"
    TOPIC_DRIFT = "topic_drift"
    SEMANTIC_DRIFT = "semantic_drift"
    TOXICITY = "toxicity"
    QUALITY_DEGRADATION = "quality_degradation"


class DetectionResult(BaseModel):
    """Result from a single failure detector."""
    failure_type: FailureType
    detected: bool
    risk_level: RiskLevel
    score: float = Field(ge=0.0, le=1.0, description="Risk score 0–1")
    details: Dict[str, Any] = Field(default_factory=dict)
    matched_patterns: List[str] = Field(default_factory=list)
    timestamp: datetime = Field(default_factory=datetime.utcnow)


class WatchResult(BaseModel):
    """Aggregated result from watching an LLM response."""
    prompt: str
    response: str
    passed: bool
    overall_risk: RiskLevel
    overall_score: float = Field(ge=0.0, le=1.0)
    detections: List[DetectionResult] = Field(default_factory=list)
    alerts_fired: List[str] = Field(default_factory=list)
    latency_ms: float = 0.0
    timestamp: datetime = Field(default_factory=datetime.utcnow)

    def to_dict(self) -> Dict[str, Any]:
        """Serialize to plain dict."""
        return self.model_dump(mode="json")


class AlertEvent(BaseModel):
    """An alert event fired when a threshold is breached."""
    alert_id: str
    failure_type: FailureType
    risk_level: RiskLevel
    score: float
    prompt: str
    response: str
    timestamp: datetime = Field(default_factory=datetime.utcnow)
    metadata: Dict[str, Any] = Field(default_factory=dict)


class DriftSnapshot(BaseModel):
    """A snapshot of metric distributions for drift detection."""
    snapshot_id: str
    metrics: Dict[str, List[float]]
    timestamp: datetime = Field(default_factory=datetime.utcnow)
