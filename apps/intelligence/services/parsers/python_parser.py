"""
Python parser — wraps the existing CodeParser for the multi-language registry.
"""
from apps.intelligence.services.parser import CodeParser, ParsedFile
from .base import BaseParser


class PythonParser(BaseParser):
    language = 'python'

    def __init__(self):
        self._parser = CodeParser()

    def parse(self, source_code: bytes, file_path: str = '') -> ParsedFile:
        result = self._parser.parse_file(source_code, file_path)
        result.language = 'python'
        return result
