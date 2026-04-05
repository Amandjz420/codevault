"""
JavaScript/TypeScript parser using regex-based extraction.
Extracts functions, classes, React components, Express routes, exports.
"""
import re
import logging
from typing import List, Optional
from apps.intelligence.services.parser import (
    ParsedFile, ParsedFunction, ParsedClass, ParsedEndpoint,
)
from .base import BaseParser

logger = logging.getLogger(__name__)


class JavaScriptParser(BaseParser):
    language = 'javascript'

    def parse(self, source_code: bytes, file_path: str = '') -> ParsedFile:
        result = ParsedFile(language='javascript' if file_path.endswith(('.js', '.jsx')) else 'typescript')
        src = self._safe_decode(source_code)
        lines = src.splitlines()

        try:
            result.imports = self._extract_imports(src)
            result.functions = self._extract_functions(src, lines)
            result.classes = self._extract_classes(src, lines)
            result.endpoints = self._extract_routes(src, lines, file_path)
        except Exception as e:
            logger.error(f"[JSParser] Error parsing {file_path}: {e}")
            result.errors.append(str(e))

        return result

    def _extract_imports(self, src: str) -> List[str]:
        imports = []
        # ES6 imports
        for m in re.finditer(r"^import\s+.+?(?:from\s+['\"].+?['\"])?;?\s*$", src, re.MULTILINE):
            imports.append(m.group().strip())
        # CommonJS require
        for m in re.finditer(r"^(?:const|let|var)\s+.+?=\s*require\s*\(.+?\)\s*;?\s*$", src, re.MULTILINE):
            imports.append(m.group().strip())
        return imports

    def _extract_functions(self, src: str, lines: List[str]) -> List[ParsedFunction]:
        results = []
        seen = set()

        patterns = [
            # Named function declarations: function name(...)
            re.compile(r'^(\s*)(export\s+)?(?:async\s+)?function\s+(\w+)\s*\(', re.MULTILINE),
            # Arrow functions: const name = (...) =>
            re.compile(r'^(\s*)(export\s+)?(?:const|let|var)\s+(\w+)\s*=\s*(?:async\s+)?\(?.*?\)?\s*=>', re.MULTILINE),
            # Method definitions in objects/classes: name(...) {
            re.compile(r'^(\s+)(?:async\s+)?(\w+)\s*\([^)]*\)\s*\{', re.MULTILINE),
        ]

        for pattern in patterns:
            for m in pattern.finditer(src):
                groups = m.groups()
                name = groups[-1] if len(groups) == 3 else groups[1]
                if not name or name in seen or name in ('if', 'for', 'while', 'switch', 'catch', 'return'):
                    continue
                seen.add(name)

                start_line = src[:m.start()].count('\n') + 1
                is_async = 'async' in m.group()

                # Extract code block (approximate)
                code_lines = []
                brace_count = 0
                started = False
                for i in range(start_line - 1, min(len(lines), start_line + 80)):
                    code_lines.append(lines[i])
                    brace_count += lines[i].count('{') - lines[i].count('}')
                    if '{' in lines[i]:
                        started = True
                    if started and brace_count <= 0:
                        break

                results.append(ParsedFunction(
                    name=name,
                    code='\n'.join(code_lines)[:2000],
                    start_line=start_line,
                    end_line=start_line + len(code_lines),
                    is_method=len(groups[0] if groups[0] else '') > 0 and pattern == patterns[2],
                    parent_class=None,
                    decorators=[],
                    docstring=self._extract_jsdoc(lines, start_line - 1),
                    is_async=is_async,
                ))

        return results

    def _extract_jsdoc(self, lines: List[str], func_line_idx: int) -> Optional[str]:
        """Look for JSDoc comment above a function."""
        if func_line_idx <= 0:
            return None
        # Scan upward for /** ... */
        for i in range(func_line_idx - 1, max(-1, func_line_idx - 15), -1):
            stripped = lines[i].strip()
            if stripped.endswith('*/'):
                doc_lines = []
                for j in range(i, max(-1, i - 30), -1):
                    doc_lines.insert(0, lines[j].strip())
                    if lines[j].strip().startswith('/**'):
                        return '\n'.join(doc_lines)
            elif stripped and not stripped.startswith('//') and not stripped.startswith('*'):
                break
        return None

    def _extract_classes(self, src: str, lines: List[str]) -> List[ParsedClass]:
        results = []
        pattern = re.compile(
            r'^(?:export\s+)?(?:default\s+)?class\s+(\w+)(?:\s+extends\s+([\w.]+))?',
            re.MULTILINE,
        )
        for m in pattern.finditer(src):
            name = m.group(1)
            base = m.group(2)
            bases = [base] if base else []
            start_line = src[:m.start()].count('\n') + 1

            # Check if it's a React component
            is_react = base in ('Component', 'PureComponent', 'React.Component', 'React.PureComponent') if base else False

            # Extract code
            code_lines = []
            brace_count = 0
            started = False
            for i in range(start_line - 1, min(len(lines), start_line + 200)):
                code_lines.append(lines[i])
                brace_count += lines[i].count('{') - lines[i].count('}')
                if '{' in lines[i]:
                    started = True
                if started and brace_count <= 0:
                    break

            results.append(ParsedClass(
                name=name,
                code='\n'.join(code_lines)[:2000],
                start_line=start_line,
                end_line=start_line + len(code_lines),
                bases=bases,
                is_django_model=False,
                fields=[],
                docstring=self._extract_jsdoc(lines, start_line - 1),
            ))

        return results

    def _extract_routes(self, src: str, lines: List[str], file_path: str) -> List[ParsedEndpoint]:
        """Extract Express.js/Next.js/Fastify routes."""
        endpoints = []

        # Express-style routes: app.get('/path', handler) or router.post(...)
        pattern = re.compile(
            r'(?:app|router)\.(get|post|put|patch|delete|all)\s*\(\s*[\'"]([^\'"]+)[\'"]',
            re.MULTILINE | re.IGNORECASE,
        )
        for m in pattern.finditer(src):
            method = m.group(1).upper()
            url = m.group(2)
            start_line = src[:m.start()].count('\n') + 1
            endpoints.append(ParsedEndpoint(
                url_pattern=url,
                view_name=f'{method} {url}',
                http_methods=[method],
                start_line=start_line,
            ))

        # Next.js API route file convention
        if '/api/' in file_path or file_path.startswith('pages/api/') or file_path.startswith('app/api/'):
            for func_match in re.finditer(r'export\s+(?:async\s+)?function\s+(GET|POST|PUT|PATCH|DELETE|HEAD|OPTIONS)\b', src):
                method = func_match.group(1)
                start_line = src[:func_match.start()].count('\n') + 1
                endpoints.append(ParsedEndpoint(
                    url_pattern=file_path,
                    view_name=method,
                    http_methods=[method],
                    start_line=start_line,
                ))

        return endpoints
