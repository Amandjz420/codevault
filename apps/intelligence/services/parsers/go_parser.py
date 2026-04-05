"""
Go parser using regex-based extraction.
Extracts functions, methods, structs, interfaces, and HTTP handlers.
"""
import re
import logging
from typing import List, Optional
from apps.intelligence.services.parser import (
    ParsedFile, ParsedFunction, ParsedClass, ParsedEndpoint,
)
from .base import BaseParser

logger = logging.getLogger(__name__)


class GoParser(BaseParser):
    language = 'go'

    def parse(self, source_code: bytes, file_path: str = '') -> ParsedFile:
        result = ParsedFile(language='go')
        src = self._safe_decode(source_code)
        lines = src.splitlines()

        try:
            result.imports = self._extract_imports(src)
            result.functions = self._extract_functions(src, lines)
            result.classes = self._extract_structs(src, lines)
            result.endpoints = self._extract_http_handlers(src, lines)
        except Exception as e:
            logger.error(f"[GoParser] Error parsing {file_path}: {e}")
            result.errors.append(str(e))

        return result

    def _extract_imports(self, src: str) -> List[str]:
        imports = []
        # Single import
        for m in re.finditer(r'^import\s+"([^"]+)"', src, re.MULTILINE):
            imports.append(f'import "{m.group(1)}"')
        # Block import
        for m in re.finditer(r'import\s*\((.*?)\)', src, re.DOTALL):
            for line in m.group(1).splitlines():
                line = line.strip().strip('"')
                if line and not line.startswith('//'):
                    imports.append(f'import "{line}"')
        return imports

    def _extract_functions(self, src: str, lines: List[str]) -> List[ParsedFunction]:
        results = []
        # func Name(args) returnType { ... }
        # func (r *Receiver) Name(args) returnType { ... }
        pattern = re.compile(
            r'^func\s+(?:\((\w+)\s+\*?(\w+)\)\s+)?(\w+)\s*\(([^)]*)\)',
            re.MULTILINE,
        )
        for m in pattern.finditer(src):
            receiver_var = m.group(1)
            receiver_type = m.group(2)
            name = m.group(3)
            start_line = src[:m.start()].count('\n') + 1
            is_method = receiver_type is not None

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

            # Look for doc comment above
            docstring = self._extract_go_doc(lines, start_line - 1)

            results.append(ParsedFunction(
                name=name,
                code='\n'.join(code_lines)[:2000],
                start_line=start_line,
                end_line=start_line + len(code_lines),
                is_method=is_method,
                parent_class=receiver_type,
                decorators=[],
                docstring=docstring,
                is_async=False,
            ))

        return results

    def _extract_go_doc(self, lines: List[str], func_line_idx: int) -> Optional[str]:
        """Extract Go doc comment (// lines above function)."""
        doc_lines = []
        for i in range(func_line_idx - 1, max(-1, func_line_idx - 20), -1):
            stripped = lines[i].strip()
            if stripped.startswith('//'):
                doc_lines.insert(0, stripped[2:].strip())
            else:
                break
        return '\n'.join(doc_lines) if doc_lines else None

    def _extract_structs(self, src: str, lines: List[str]) -> List[ParsedClass]:
        results = []
        # type Name struct { ... }
        pattern = re.compile(r'^type\s+(\w+)\s+(struct|interface)\s*\{', re.MULTILINE)
        for m in pattern.finditer(src):
            name = m.group(1)
            kind = m.group(2)
            start_line = src[:m.start()].count('\n') + 1

            # Extract fields
            code_lines = []
            fields = []
            brace_count = 0
            started = False
            for i in range(start_line - 1, min(len(lines), start_line + 100)):
                code_lines.append(lines[i])
                brace_count += lines[i].count('{') - lines[i].count('}')
                if '{' in lines[i]:
                    started = True
                # Extract struct fields
                if started and kind == 'struct':
                    field_match = re.match(r'^\s+(\w+)\s+(\S+)', lines[i])
                    if field_match and field_match.group(1)[0].isupper():
                        fields.append({
                            'name': field_match.group(1),
                            'type': field_match.group(2),
                        })
                if started and brace_count <= 0:
                    break

            results.append(ParsedClass(
                name=name,
                code='\n'.join(code_lines)[:2000],
                start_line=start_line,
                end_line=start_line + len(code_lines),
                bases=[kind],  # 'struct' or 'interface'
                is_django_model=False,
                fields=fields,
                docstring=self._extract_go_doc(lines, start_line - 1),
            ))

        return results

    def _extract_http_handlers(self, src: str, lines: List[str]) -> List[ParsedEndpoint]:
        """Extract net/http or Gin/Echo/Fiber route registrations."""
        endpoints = []

        # Standard: http.HandleFunc("/path", handler)
        # Mux: r.HandleFunc("/path", handler).Methods("GET")
        # Gin: r.GET("/path", handler)
        patterns = [
            re.compile(r'(?:Handle|HandleFunc)\s*\(\s*"([^"]+)"\s*,\s*(\w+)', re.MULTILINE),
            re.compile(r'\.(GET|POST|PUT|PATCH|DELETE|HEAD)\s*\(\s*"([^"]+)"\s*,\s*(\w+)', re.MULTILINE),
        ]

        for pattern in patterns:
            for m in pattern.finditer(src):
                if len(m.groups()) == 2:
                    url, handler = m.group(1), m.group(2)
                    methods = []
                else:
                    method, url, handler = m.group(1), m.group(2), m.group(3)
                    methods = [method]

                start_line = src[:m.start()].count('\n') + 1
                endpoints.append(ParsedEndpoint(
                    url_pattern=url,
                    view_name=handler,
                    http_methods=methods,
                    start_line=start_line,
                ))

        return endpoints
