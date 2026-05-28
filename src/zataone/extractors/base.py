# zataone signal extractor base

from __future__ import annotations
from abc import ABC, abstractmethod
from typing import Any


class BaseExtractor(ABC):
    """Base interface for signal extractors. AI models are sensors—extract signals only."""

    extractor_id: str
    version: str

    @abstractmethod
    def extract(self, asset: Any) -> Any:
        """
        Extract signals from an asset.

        Args:
            asset: Normalized asset (content + metadata).

        Returns:
            Extracted signals (structure TBD per extractor).
        """
        pass
