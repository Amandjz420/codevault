"""
Base parser interface for all language parsers.
"""
import logging
from abc import ABC, abstractmethod
from apps.intelligence.services.parser import ParsedFile

logger = logging.getLogger(__name__)


class BaseParser(ABC):
    """Abstract base for all language-specific parsers."""

    language: str = 'unknown'

    @abstractmethod
    def parse(self, source_code: bytes, file_path: str = '') -> ParsedFile:
        """Parse source code and return extracted entities."""
        ...

    def _safe_decode(self, source: bytes) -> str:
        return source.decode('utf-8', errors='replace')
