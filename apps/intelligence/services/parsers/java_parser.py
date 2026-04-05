"""
Java parser using regex-based extraction.
Extracts classes, methods, interfaces, Spring endpoints, and annotations.
"""
import re
import logging
from typing import List, Optional
from apps.intelligence.services.parser import (
    ParsedFile, ParsedFunction, ParsedClass, ParsedEndpoint,
)
from .base import BaseParser

logger = logging.getLogger(__name__)


class JavaParser(BaseParser):
    language = 'java'

    def parse(self, source_code: bytes, file_path: str = '') -> ParsedFile:
        result = ParsedFile(language='java')
        src = self._safe_decode(source_code)
        lines = src.splitlines()

        try:
            result.imports = self._extract_imports(src)
            result.functions = self._extract_methods(src, lines)
            result.classes = self._extract_classes(src, lines)
            result.endpoints = self._extract_spring_endpoints(src, lines)
        except Exception as e:
            logger.error(f"[JavaParser] Error parsing {file_path}: {e}")
            result.errors.append(str(e))

        return result

    def _extract_imports(self, src: str) -> List[str]:
        imports = []
        for m in re.finditer(r'^import\s+(?:static\s+)?[\w.*]+\s*;', src, re.MULTILINE):
            imports.append(m.group().strip())
        return imports

    def _extract_methods(self, src: str, lines: List[str]) -> List[ParsedFunction]:
        results = []
        # Match methods: modifiers returnType name(args) { or throws ...{
        pattern = re.compile(
            r'^(\s+)((?:public|private|protected|static|final|abstract|synchronized|native)\s+)*'
            r'(?:<[\w\s,?]+>\s+)?'
            r'([\w<>\[\],\s?]+)\s+(\w+)\s*\(([^)]*)\)',
            re.MULTILINE,
        )
        for m in pattern.finditer(src):
            indent = m.group(1)
            name = m.group(4)
            return_type = m.group(3).strip()
            start_line = src[:m.start()].count('\n') + 1

            # Skip constructors matching class names and common non-methods
            if name in ('if', 'for', 'while', 'switch', 'catch', 'return', 'class', 'new'):
                continue

            # Detect parent class
            parent_class = None
            for i in range(start_line - 2, max(-1, start_line - 100), -1):
                cls_match = re.match(r'^\s*(?:public\s+)?(?:abstract\s+)?(?:final\s+)?class\s+(\w+)', lines[i])
                if cls_match:
                    parent_class = cls_match.group(1)
                    break

            # Extract annotations
            annotations = []
            for i in range(start_line - 2, max(-1, start_line - 10), -1):
                stripped = lines[i].strip()
                if stripped.startswith('@'):
                    annotations.insert(0, stripped)
                elif stripped and not stripped.startswith('//') and not stripped.startswith('/*') and not stripped.startswith('*'):
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

            # Javadoc
            docstring = self._extract_javadoc(lines, start_line - 1, annotations)

            results.append(ParsedFunction(
                name=name,
                code='\n'.join(code_lines)[:2000],
                start_line=start_line,
                end_line=start_line + len(code_lines),
                is_method=True,
                parent_class=parent_class,
                decorators=annotations,
                docstring=docstring,
                is_async=False,
            ))

        return results

    def _extract_javadoc(self, lines: List[str], func_line_idx: int, annotations: List[str]) -> Optional[str]:
        """Extract Javadoc comment above a method."""
        start = func_line_idx - 1 - len(annotations)
        for i in range(start, max(-1, start - 5), -1):
            if lines[i].strip().endswith('*/'):
                doc_lines = []
                for j in range(i, max(-1, i - 30), -1):
                    doc_lines.insert(0, lines[j].strip())
                    if lines[j].strip().startswith('/**'):
                        return '\n'.join(doc_lines)
        return None

    def _extract_classes(self, src: str, lines: List[str]) -> List[ParsedClass]:
        results = []
        pattern = re.compile(
            r'^(?:public\s+)?(?:abstract\s+)?(?:final\s+)?'
            r'(class|interface|enum|record)\s+(\w+)'
            r'(?:<[^>]*>)?'
            r'(?:\s+extends\s+([\w.]+))?'
            r'(?:\s+implements\s+([\w.,\s]+))?',
            re.MULTILINE,
        )
        for m in pattern.finditer(src):
            kind = m.group(1)
            name = m.group(2)
            extends = m.group(3)
            implements = m.group(4)

            bases = []
            if extends:
                bases.append(extends)
            if implements:
                bases.extend([b.strip() for b in implements.split(',')])
            if not bases:
                bases = [kind]

            start_line = src[:m.start()].count('\n') + 1

            # Extract annotations
            annotations = []
            for i in range(start_line - 2, max(-1, start_line - 10), -1):
                stripped = lines[i].strip()
                if stripped.startswith('@'):
                    annotations.insert(0, stripped)
                else:
                    break

            code_lines = []
            brace_count = 0
            started = False
            for i in range(start_line - 1, min(len(lines), start_line + 300)):
                code_lines.append(lines[i])
                brace_count += lines[i].count('{') - lines[i].count('}')
                if '{' in lines[i]:
                    started = True
                if started and brace_count <= 0:
                    break

            # Check for Spring entity
            is_entity = any('@Entity' in a or '@Table' in a for a in annotations)

            # Extract fields
            fields = []
            if kind in ('class', 'record'):
                for line in code_lines[1:]:
                    field_match = re.match(
                        r'^\s+(?:private|protected|public)\s+(?:(?:final|static|transient)\s+)*(\S+)\s+(\w+)\s*[;=]',
                        line,
                    )
                    if field_match:
                        fields.append({
                            'name': field_match.group(2),
                            'type': field_match.group(1),
                        })

            results.append(ParsedClass(
                name=name,
                code='\n'.join(code_lines)[:2000],
                start_line=start_line,
                end_line=start_line + len(code_lines),
                bases=bases,
                is_django_model=is_entity,  # reuse field for ORM entity detection
                fields=fields,
                docstring=self._extract_javadoc(lines, start_line - 1, annotations),
            ))

        return results

    def _extract_spring_endpoints(self, src: str, lines: List[str]) -> List[ParsedEndpoint]:
        """Extract Spring MVC/Boot REST endpoints."""
        endpoints = []

        # Find class-level @RequestMapping
        class_prefix = ''
        class_mapping = re.search(r'@RequestMapping\s*\(\s*(?:value\s*=\s*)?["\']([^"\']+)', src)
        if class_mapping:
            class_prefix = class_mapping.group(1)

        # Method-level mappings
        pattern = re.compile(
            r'@(GetMapping|PostMapping|PutMapping|PatchMapping|DeleteMapping|RequestMapping)'
            r'\s*\(\s*(?:value\s*=\s*)?(?:["\']([^"\']*)["\'])?[^)]*\)\s*'
            r'(?:public\s+)?(?:\w+(?:<[^>]+>)?\s+)?(\w+)\s*\(',
            re.MULTILINE | re.DOTALL,
        )
        for m in pattern.finditer(src):
            annotation = m.group(1)
            url = m.group(2) or ''
            handler = m.group(3)
            start_line = src[:m.start()].count('\n') + 1

            method_map = {
                'GetMapping': 'GET',
                'PostMapping': 'POST',
                'PutMapping': 'PUT',
                'PatchMapping': 'PATCH',
                'DeleteMapping': 'DELETE',
                'RequestMapping': 'ANY',
            }
            method = method_map.get(annotation, 'ANY')

            full_url = class_prefix + url
            endpoints.append(ParsedEndpoint(
                url_pattern=full_url,
                view_name=handler,
                http_methods=[method],
                start_line=start_line,
            ))

        return endpoints
