# zataone extractor registry

from __future__ import annotations
from typing import Type

from zataone.extractors.base import BaseExtractor


class ExtractorRegistry:
    """Registry for modular signal extractors. Versioned, pluggable extractors."""

    def __init__(self) -> None:
        self._extractors: dict[str, BaseExtractor] = {}

    def register(self, extractor: BaseExtractor) -> None:
        """
        Register an extractor. Overwrites if extractor_id already exists.

        Args:
            extractor: Extractor instance (must have extractor_id and version).
        """
        self._extractors[extractor.extractor_id] = extractor

    def get(self, extractor_id: str) -> BaseExtractor | None:
        """
        Get an extractor by ID.

        Args:
            extractor_id: Unique extractor identifier.

        Returns:
            Extractor instance or None if not found.
        """
        return self._extractors.get(extractor_id)

    def list(self) -> list[BaseExtractor]:
        """
        List all registered extractors.

        Returns:
            List of extractor instances.
        """
        return list(self._extractors.values())
