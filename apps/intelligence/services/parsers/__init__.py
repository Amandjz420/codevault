"""
Multi-language parser registry.
Maps file extensions to their respective parser classes.
"""
from .python_parser import PythonParser
from .javascript_parser import JavaScriptParser
from .go_parser import GoParser
from .rust_parser import RustParser
from .java_parser import JavaParser
from .markdown_parser import MarkdownParser
from .json_parser import JSONParser
from .base import BaseParser

PARSER_REGISTRY = {
    '.py': PythonParser,
    '.js': JavaScriptParser,
    '.jsx': JavaScriptParser,
    '.ts': JavaScriptParser,
    '.tsx': JavaScriptParser,
    '.go': GoParser,
    '.rs': RustParser,
    '.java': JavaParser,
    '.md': MarkdownParser,
    '.mdx': MarkdownParser,
    '.json': JSONParser,
}

SUPPORTED_EXTENSIONS = set(PARSER_REGISTRY.keys())


def get_parser_for_file(file_path: str) -> BaseParser:
    """Return the appropriate parser for a file based on its extension."""
    import os
    ext = os.path.splitext(file_path)[1].lower()
    parser_cls = PARSER_REGISTRY.get(ext)
    if parser_cls:
        return parser_cls()
    return None


def get_supported_extensions() -> set:
    return SUPPORTED_EXTENSIONS
