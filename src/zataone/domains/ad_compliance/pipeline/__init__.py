"""
Compliance pipeline orchestration.

Orchestrates the flow: Asset → Signals → Violations → Outcome
"""

from __future__ import annotations
from .engine import CompliancePipeline

__all__ = ['CompliancePipeline']
