"""
Core data models for the compliance pipeline.
"""

from __future__ import annotations
from dataclasses import dataclass, field
from typing import List, Optional, Dict, Any
from datetime import datetime
from enum import Enum


class SignalType(str, Enum):
    """Types of signals that can be detected."""
    TEXT = "text"
    OBJECT = "object"
    FACE = "face"
    BRAND = "brand"
    SCENE = "scene"


class ViolationSeverity(str, Enum):
    """Severity levels for violations."""
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"
    CRITICAL = "CRITICAL"


class ComplianceStatus(str, Enum):
    """Final compliance status."""
    COMPLIANT = "COMPLIANT"
    NON_COMPLIANT = "NON_COMPLIANT"
    REVIEW_REQUIRED = "REVIEW_REQUIRED"


@dataclass
class Asset:
    """Input image asset with metadata."""
    image_id: str
    image_data: bytes  # Raw image bytes
    filename: str
    content_type: str
    uploaded_at: datetime = field(default_factory=datetime.now)
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class Signal:
    """Detected signal from a model (text, object, etc.)."""
    signal_id: str
    signal_type: SignalType
    source_model: str  # e.g., "ocr", "vlm", "object_detector"
    confidence: float  # 0.0 to 1.0
    raw_data: Dict[str, Any]  # Model-specific output
    bounding_box: Optional[Dict[str, float]] = None  # x, y, width, height if applicable
    detected_at: datetime = field(default_factory=datetime.now)


@dataclass
class Evidence:
    """Supporting evidence for a violation."""
    evidence_id: str
    violation_id: str
    signal_id: str
    evidence_type: str  # e.g., "text_match", "object_detection", "context"
    description: str
    data: Dict[str, Any] = field(default_factory=dict)


@dataclass
class Violation:
    """A compliance rule violation."""
    violation_id: str
    rule_id: str
    rule_name: str
    severity: ViolationSeverity
    description: str
    evidence: List[Evidence] = field(default_factory=list)
    detected_at: datetime = field(default_factory=datetime.now)


class Verdict(str, Enum):
    """Final verdict for compliance assessment."""
    LIKELY_APPROVED = "likely_approved"
    BORDERLINE = "borderline"
    LIKELY_REJECTED = "likely_rejected"


@dataclass
class Outcome:
    """Final compliance assessment result."""
    outcome_id: str
    asset_id: str
    status: ComplianceStatus
    risk_score: float  # 0.0 to 1.0
    verdict: Verdict  # likely_approved, borderline, likely_rejected
    violations: List[Violation] = field(default_factory=list)
    signals: List[Signal] = field(default_factory=list)
    fix_suggestions: List[str] = field(default_factory=list)
    processed_at: datetime = field(default_factory=datetime.now)
    metadata: Dict[str, Any] = field(default_factory=dict)
