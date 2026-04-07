"""
Markdown parser — treats the entire file as a single document.

Since .md files have no functions/classes/endpoints, the ParsedFile is
returned with all entity lists empty. The raw text is stored so that:
  - The vector store can embed it for semantic search
  - generate_file_description() can summarise it via LLM
  - IndexedFile.content is populated for full-text access
"""
import re
from apps.intelligence.services.parser import ParsedFile
from .base import BaseParser


class MarkdownParser(BaseParser):
    language = 'markdown'

    def parse(self, source_code: bytes, file_path: str = '') -> ParsedFile:
        return ParsedFile(language='markdown')
