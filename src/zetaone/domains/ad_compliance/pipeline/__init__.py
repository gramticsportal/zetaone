"""
Compliance pipeline orchestration.

Orchestrates the flow: Asset → Signals → Violations → Outcome
"""

from .engine import CompliancePipeline

__all__ = ['CompliancePipeline']
