"""
Rust parser using regex-based extraction.
Extracts functions, structs, traits, impl blocks, and Actix/Axum routes.
"""
import re
import logging
from typing import List, Optional
from apps.intelligence.services.parser import (
    ParsedFile, ParsedFunction, ParsedClass, ParsedEndpoint,
)
from .base import BaseParser

logger = logging.getLogger(__name__)


class RustParser(BaseParser):
    language = 'rust'

    def parse(self, source_code: bytes, file_path: str = '') -> ParsedFile:
        result = ParsedFile(language='rust')
        src = self._safe_decode(source_code)
        lines = src.splitlines()

        try:
            result.imports = self._extract_imports(src)
            result.functions = self._extract_functions(src, lines)
            result.classes = self._extract_structs_and_traits(src, lines)
            result.endpoints = self._extract_routes(src, lines)
        except Exception as e:
            logger.error(f"[RustParser] Error parsing {file_path}: {e}")
            result.errors.append(str(e))

        return result

    def _extract_imports(self, src: str) -> List[str]:
        imports = []
        for m in re.finditer(r'^use\s+.+;', src, re.MULTILINE):
            imports.append(m.group().strip())
        return imports

    def _extract_functions(self, src: str, lines: List[str]) -> List[ParsedFunction]:
        results = []
        # pub fn name(args) -> ReturnType { ... }
        # async fn name(args) -> ReturnType { ... }
        pattern = re.compile(
            r'^(\s*)(pub(?:\(crate\))?\s+)?(?:async\s+)?fn\s+(\w+)',
            re.MULTILINE,
        )
        for m in pattern.finditer(src):
            indent = m.group(1)
            name = m.group(3)
            start_line = src[:m.start()].count('\n') + 1
            is_async = 'async' in m.group()
            is_method = len(indent) > 0

            # Detect parent impl block
            parent_class = None
            if is_method:
                for i in range(start_line - 2, max(-1, start_line - 50), -1):
                    impl_match = re.match(r'^impl(?:<[^>]*>)?\s+(\w+)', lines[i])
                    if impl_match:
                        parent_class = impl_match.group(1)
                        break

            # Extract decorators (attributes like #[...])
            decorators = []
            for i in range(start_line - 2, max(-1, start_line - 10), -1):
                stripped = lines[i].strip()
                if stripped.startswith('#['):
                    decorators.insert(0, stripped)
                elif stripped and not stripped.startswith('//'):
                    break

            # Extract code block
            code_lines = []
            brace_count = 0
            started = False
            for i in range(start_line - 1, min(len(lines), start_line + 100)):
                code_lines.append(lines[i])
                brace_count += lines[i].count('{') - lines[i].count('}')
                if '{' in lines[i]:
                    started = True
                if started and brace_count <= 0:
                    break

            # Doc comment
            docstring = self._extract_rust_doc(lines, start_line - 1, decorators)

            results.append(ParsedFunction(
                name=name,
                code='\n'.join(code_lines)[:2000],
                start_line=start_line,
                end_line=start_line + len(code_lines),
                is_method=is_method,
                parent_class=parent_class,
                decorators=decorators,
                docstring=docstring,
                is_async=is_async,
            ))

        return results

    def _extract_rust_doc(self, lines: List[str], func_line_idx: int, decorators: List[str]) -> Optional[str]:
        """Extract /// doc comments above a function."""
        doc_lines = []
        start = func_line_idx - 1 - len(decorators)
        for i in range(start, max(-1, start - 20), -1):
            stripped = lines[i].strip()
            if stripped.startswith('///'):
                doc_lines.insert(0, stripped[3:].strip())
            elif stripped.startswith('//!'):
                doc_lines.insert(0, stripped[3:].strip())
            else:
                break
        return '\n'.join(doc_lines) if doc_lines else None

    def _extract_structs_and_traits(self, src: str, lines: List[str]) -> List[ParsedClass]:
        results = []
        # struct Name { ... } or trait Name { ... } or enum Name { ... }
        pattern = re.compile(
            r'^(pub(?:\(crate\))?\s+)?(struct|trait|enum)\s+(\w+)(?:<[^>]*>)?(?:\s*:\s*(.+?))?\s*\{',
            re.MULTILINE,
        )
        for m in pattern.finditer(src):
            kind = m.group(2)
            name = m.group(3)
            bases_str = m.group(4)
            bases = [b.strip() for b in bases_str.split('+')] if bases_str else [kind]
            start_line = src[:m.start()].count('\n') + 1

            code_lines = []
            fields = []
            brace_count = 0
            started = False
            for i in range(start_line - 1, min(len(lines), start_line + 100)):
                code_lines.append(lines[i])
                brace_count += lines[i].count('{') - lines[i].count('}')
                if '{' in lines[i]:
                    started = True
                if started and kind == 'struct':
                    field_match = re.match(r'^\s+(pub\s+)?(\w+)\s*:\s*(.+?),?\s*$', lines[i])
                    if field_match:
                        fields.append({
                            'name': field_match.group(2),
                            'type': field_match.group(3).rstrip(','),
                        })
                if started and brace_count <= 0:
                    break

            results.append(ParsedClass(
                name=name,
                code='\n'.join(code_lines)[:2000],
                start_line=start_line,
                end_line=start_line + len(code_lines),
                bases=bases,
                is_django_model=False,
                fields=fields,
                docstring=self._extract_rust_doc(lines, start_line - 1, []),
            ))

        return results

    def _extract_routes(self, src: str, lines: List[str]) -> List[ParsedEndpoint]:
        """Extract Actix-web or Axum route attributes."""
        endpoints = []
        # Actix: #[get("/path")] or #[post("/path")]
        pattern = re.compile(r'#\[(get|post|put|patch|delete|head)\s*\(\s*"([^"]+)"\s*\)\]', re.IGNORECASE)
        for m in pattern.finditer(src):
            method = m.group(1).upper()
            url = m.group(2)
            start_line = src[:m.start()].count('\n') + 1

            # Find handler function name
            handler = 'unknown'
            for i in range(start_line, min(len(lines), start_line + 5)):
                fn_match = re.search(r'(?:async\s+)?fn\s+(\w+)', lines[i])
                if fn_match:
                    handler = fn_match.group(1)
                    break

            endpoints.append(ParsedEndpoint(
                url_pattern=url,
                view_name=handler,
                http_methods=[method],
                start_line=start_line,
            ))

        return endpoints
