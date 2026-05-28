"""
Internal data models for the compliance system.

Defines the core data structures:
- Asset: Input image and metadata
- Signal: Detected features from models (text, objects, etc.)
- Violation: Compliance rule violations
- Evidence: Supporting data for violations
- Outcome: Final compliance assessment
"""

from __future__ import annotations
from .models import Asset, Signal, Violation, Evidence, Outcome, Verdict

__all__ = ['Asset', 'Signal', 'Violation', 'Evidence', 'Outcome', 'Verdict']
