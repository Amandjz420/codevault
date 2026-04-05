"""
Tree-sitter based AST parser for Python files.
Extracts functions, classes, Django model fields, API endpoints, signals, and Celery crons.
"""
import re
import logging
from dataclasses import dataclass, field
from typing import List, Optional

logger = logging.getLogger(__name__)


@dataclass
class ParsedFunction:
    name: str
    code: str
    start_line: int
    end_line: int
    is_method: bool
    parent_class: Optional[str]
    decorators: List[str]
    docstring: Optional[str]
    is_async: bool


@dataclass
class ParsedClass:
    name: str
    code: str
    start_line: int
    end_line: int
    bases: List[str]
    is_django_model: bool
    fields: List[dict]  # {name, type} for model fields
    docstring: Optional[str]


@dataclass
class ParsedEndpoint:
    url_pattern: str
    view_name: str
    http_methods: List[str]
    start_line: int


@dataclass
class ParsedSignal:
    signal_type: str   # post_save, pre_delete, etc.
    sender: Optional[str]
    handler_function: str
    start_line: int


@dataclass
class ParsedCronJob:
    task_name: str
    schedule: str
    start_line: int


@dataclass
class ParsedFile:
    language: str = 'python'
    functions: List[ParsedFunction] = field(default_factory=list)
    classes: List[ParsedClass] = field(default_factory=list)
    endpoints: List[ParsedEndpoint] = field(default_factory=list)
    signals: List[ParsedSignal] = field(default_factory=list)
    cron_jobs: List[ParsedCronJob] = field(default_factory=list)
    imports: List[str] = field(default_factory=list)
    errors: List[str] = field(default_factory=list)


class CodeParser:
    """Parses Python source files using Tree-sitter."""

    def __init__(self):
        self._init_parser()

    def _init_parser(self):
        try:
            import tree_sitter_languages
            from tree_sitter import Parser
            self.py_language = tree_sitter_languages.get_language('python')
            self.parser = Parser()
            self.parser.set_language(self.py_language)
            self._available = True
        except Exception as e:
            logger.warning(f"[CodeParser] tree-sitter unavailable: {e}. Falling back to regex parser.")
            self._available = False

    def parse_file(self, source_code: bytes, file_path: str = '') -> ParsedFile:
        """Parse a Python file and return all extracted entities."""
        result = ParsedFile()
        if self._available:
            try:
                tree = self.parser.parse(source_code)
                result.imports = self._extract_imports(tree, source_code)
                result.classes = self._extract_classes(tree, source_code)
                result.functions = self._extract_functions(tree, source_code)
                result.endpoints = self._extract_endpoints(tree, source_code, file_path)
                result.signals = self._extract_signals(tree, source_code)
                result.cron_jobs = self._extract_cron_jobs(tree, source_code)
                return result
            except Exception as e:
                logger.error(f"[CodeParser] tree-sitter parse error for {file_path}: {e}")
                result.errors.append(str(e))

        # Fallback to regex-based parsing
        try:
            src = source_code.decode('utf-8', errors='replace')
            result.imports = self._regex_imports(src)
            result.functions = self._regex_functions(src)
            result.classes = self._regex_classes(src)
            result.endpoints = self._regex_endpoints(src, file_path)
            result.signals = self._regex_signals(src)
            result.cron_jobs = self._extract_cron_jobs_regex(src)
        except Exception as e:
            logger.error(f"[CodeParser] Regex parse error for {file_path}: {e}")
            result.errors.append(str(e))

        return result

    # ------------------------------------------------------------------ #
    #  Tree-sitter helpers                                                 #
    # ------------------------------------------------------------------ #

    def _get_node_text(self, node, source: bytes) -> str:
        return source[node.start_byte:node.end_byte].decode('utf-8', errors='replace')

    def _extract_imports(self, tree, source: bytes) -> List[str]:
        imports = []
        query = self.py_language.query("""
            (import_statement) @import
            (import_from_statement) @import
        """)
        for node, _ in query.captures(tree.root_node):
            imports.append(node.text.decode('utf-8', errors='replace'))
        return imports

    def _get_decorators(self, node, source: bytes) -> List[str]:
        decorators = []
        parent = node.parent
        if parent:
            prev = node.prev_named_sibling
            while prev and prev.type == 'decorator':
                decorators.insert(0, self._get_node_text(prev, source).strip())
                prev = prev.prev_named_sibling
        return decorators

    def _get_docstring(self, node, source: bytes) -> Optional[str]:
        body = node.child_by_field_name('body')
        if body and body.named_child_count > 0:
            first = body.named_children[0]
            if first.type == 'expression_statement':
                expr = first.named_children[0] if first.named_child_count > 0 else None
                if expr and expr.type == 'string':
                    raw = self._get_node_text(expr, source)
                    return raw.strip('"\' \n')
        return None

    def _extract_functions(self, tree, source: bytes) -> List[ParsedFunction]:
        query = self.py_language.query("(function_definition) @func")
        results = []
        seen = set()

        for node, _ in query.captures(tree.root_node):
            name_node = node.child_by_field_name('name')
            if not name_node:
                continue

            name = self._get_node_text(name_node, source)
            key = (name, node.start_point[0])
            if key in seen:
                continue
            seen.add(key)

            # Check if method (parent is class body)
            is_method = False
            parent_class = None
            parent = node.parent
            if parent and parent.type == 'block':
                grandparent = parent.parent
                if grandparent and grandparent.type == 'class_definition':
                    is_method = True
                    class_name_node = grandparent.child_by_field_name('name')
                    if class_name_node:
                        parent_class = self._get_node_text(class_name_node, source)

            # Detect async
            is_async = any(child.type == 'async' for child in node.children)

            results.append(ParsedFunction(
                name=name,
                code=self._get_node_text(node, source),
                start_line=node.start_point[0] + 1,
                end_line=node.end_point[0] + 1,
                is_method=is_method,
                parent_class=parent_class,
                decorators=self._get_decorators(node, source),
                docstring=self._get_docstring(node, source),
                is_async=is_async,
            ))

        return results

    def _extract_classes(self, tree, source: bytes) -> List[ParsedClass]:
        query = self.py_language.query("(class_definition) @cls")
        results = []

        for node, _ in query.captures(tree.root_node):
            name_node = node.child_by_field_name('name')
            if not name_node:
                continue

            name = self._get_node_text(name_node, source)

            # Get base classes
            bases = []
            args = node.child_by_field_name('superclasses')
            if args:
                for child in args.named_children:
                    bases.append(self._get_node_text(child, source))

            # Detect Django model
            is_django_model = any('Model' in b or 'models.Model' in b for b in bases)

            # Extract model fields if it's a Django model
            fields = []
            if is_django_model:
                fields = self._extract_model_fields(node, source)

            results.append(ParsedClass(
                name=name,
                code=self._get_node_text(node, source),
                start_line=node.start_point[0] + 1,
                end_line=node.end_point[0] + 1,
                bases=bases,
                is_django_model=is_django_model,
                fields=fields,
                docstring=self._get_docstring(node, source),
            ))

        return results

    def _extract_model_fields(self, class_node, source: bytes) -> List[dict]:
        fields = []
        body = class_node.child_by_field_name('body')
        if not body:
            return fields

        for child in body.named_children:
            if child.type == 'expression_statement':
                continue
            if child.type == 'assignment':
                left = child.child_by_field_name('left')
                right = child.child_by_field_name('right')
                if left and right:
                    field_name = self._get_node_text(left, source)
                    field_value = self._get_node_text(right, source)
                    if 'Field' in field_value or 'Key' in field_value or 'models.' in field_value:
                        field_type = field_value.split('(')[0].strip()
                        fields.append({'name': field_name, 'type': field_type})

        return fields

    def _extract_endpoints(self, tree, source: bytes, file_path: str) -> List[ParsedEndpoint]:
        endpoints = []
        query = self.py_language.query("""
            (call
                function: (identifier) @func_name
                arguments: (argument_list) @args
            ) @call
        """)

        seen = set()
        for node, capture_name in query.captures(tree.root_node):
            if capture_name == 'func_name':
                func_text = self._get_node_text(node, source)
                if func_text in ('path', 're_path', 'url'):
                    call_node = node.parent
                    if call_node is None:
                        continue
                    args_node = call_node.child_by_field_name('arguments')
                    if args_node and args_node.named_child_count >= 2:
                        url_arg = args_node.named_children[0]
                        view_arg = args_node.named_children[1]
                        url_pattern = self._get_node_text(url_arg, source).strip("'\"")
                        view_name = self._get_node_text(view_arg, source)
                        key = (url_pattern, view_name)
                        if key not in seen:
                            seen.add(key)
                            endpoints.append(ParsedEndpoint(
                                url_pattern=url_pattern,
                                view_name=view_name,
                                http_methods=[],
                                start_line=node.start_point[0] + 1,
                            ))

        return endpoints

    def _extract_signals(self, tree, source: bytes) -> List[ParsedSignal]:
        signals = []

        # Query for @receiver(...) decorators
        query = self.py_language.query("""
            (decorated_definition
                (decorator
                    (call
                        function: (identifier) @dec_name
                        arguments: (argument_list) @args
                    )
                )
                definition: (function_definition
                    name: (identifier) @handler_name
                )
            ) @full
        """)

        for node, capture_name in query.captures(tree.root_node):
            if capture_name == 'dec_name':
                dec_text = self._get_node_text(node, source)
                if dec_text == 'receiver':
                    # Navigate to get args and handler name
                    dec_call = node.parent  # call node
                    args_node = dec_call.child_by_field_name('arguments') if dec_call else None

                    signal_type = ''
                    sender = None
                    if args_node and args_node.named_child_count >= 1:
                        signal_type = self._get_node_text(args_node.named_children[0], source)
                        if args_node.named_child_count >= 2:
                            sender_text = self._get_node_text(args_node.named_children[1], source)
                            if '=' in sender_text:
                                sender = sender_text.split('=')[-1].strip()
                            else:
                                sender = sender_text

                    # Find decorated function name
                    decorated_def = dec_call.parent.parent if dec_call and dec_call.parent else None
                    handler_name = 'unknown'
                    if decorated_def and decorated_def.type == 'decorated_definition':
                        func_def = decorated_def.child_by_field_name('definition')
                        if func_def:
                            fn_name_node = func_def.child_by_field_name('name')
                            if fn_name_node:
                                handler_name = self._get_node_text(fn_name_node, source)

                    if signal_type:
                        signals.append(ParsedSignal(
                            signal_type=signal_type,
                            sender=sender,
                            handler_function=handler_name,
                            start_line=node.start_point[0] + 1,
                        ))

        return signals

    def _extract_cron_jobs(self, tree, source: bytes) -> List[ParsedCronJob]:
        crons = []
        src = source.decode('utf-8', errors='replace')
        crons.extend(self._extract_cron_jobs_regex(src))
        return crons

    # ------------------------------------------------------------------ #
    #  Regex fallback parsers                                              #
    # ------------------------------------------------------------------ #

    def _regex_imports(self, src: str) -> List[str]:
        imports = []
        for line in src.splitlines():
            stripped = line.strip()
            if stripped.startswith('import ') or stripped.startswith('from '):
                imports.append(stripped)
        return imports

    def _regex_functions(self, src: str) -> List[ParsedFunction]:
        results = []
        lines = src.splitlines()
        func_pattern = re.compile(r'^(\s*)(async\s+)?def\s+(\w+)\s*\(', re.MULTILINE)

        for m in func_pattern.finditer(src):
            indent = len(m.group(1))
            is_async = bool(m.group(2))
            name = m.group(3)
            start_line = src[:m.start()].count('\n') + 1
            end_line = start_line  # rough approximation

            # Find class context by scanning upward
            parent_class = None
            is_method = False
            for i in range(start_line - 2, max(0, start_line - 50), -1):
                if i < len(lines):
                    line = lines[i]
                    cls_match = re.match(r'^(\s*)class\s+(\w+)', line)
                    if cls_match and len(cls_match.group(1)) < indent:
                        parent_class = cls_match.group(2)
                        is_method = True
                        break

            # Get code block (approximate)
            code_lines = [lines[start_line - 1]] if start_line <= len(lines) else []
            for j in range(start_line, min(len(lines), start_line + 60)):
                code_lines.append(lines[j])
                if j > start_line and lines[j] and not lines[j][0].isspace():
                    break

            results.append(ParsedFunction(
                name=name,
                code='\n'.join(code_lines)[:2000],
                start_line=start_line,
                end_line=start_line + len(code_lines),
                is_method=is_method,
                parent_class=parent_class,
                decorators=[],
                docstring=None,
                is_async=is_async,
            ))
        return results

    def _regex_classes(self, src: str) -> List[ParsedClass]:
        results = []
        class_pattern = re.compile(r'^class\s+(\w+)\s*(?:\(([^)]*)\))?:', re.MULTILINE)

        for m in class_pattern.finditer(src):
            name = m.group(1)
            bases_str = m.group(2) or ''
            bases = [b.strip() for b in bases_str.split(',') if b.strip()]
            is_django_model = any('Model' in b or 'models.Model' in b for b in bases)
            start_line = src[:m.start()].count('\n') + 1

            results.append(ParsedClass(
                name=name,
                code='',
                start_line=start_line,
                end_line=start_line,
                bases=bases,
                is_django_model=is_django_model,
                fields=[],
                docstring=None,
            ))
        return results

    def _regex_endpoints(self, src: str, file_path: str) -> List[ParsedEndpoint]:
        endpoints = []
        pattern = re.compile(
            r'(?:path|re_path|url)\s*\(\s*["\']([^"\']*)["\'],\s*([^\s,)]+)',
            re.MULTILINE,
        )
        for m in pattern.finditer(src):
            start_line = src[:m.start()].count('\n') + 1
            endpoints.append(ParsedEndpoint(
                url_pattern=m.group(1),
                view_name=m.group(2),
                http_methods=[],
                start_line=start_line,
            ))
        return endpoints

    def _regex_signals(self, src: str) -> List[ParsedSignal]:
        signals = []
        pattern = re.compile(
            r'@receiver\s*\(\s*([^\s,)]+)(?:,\s*sender\s*=\s*([^\s,)]+))?\s*\)\s*\n\s*(?:async\s+)?def\s+(\w+)',
            re.MULTILINE,
        )
        for m in pattern.finditer(src):
            start_line = src[:m.start()].count('\n') + 1
            signals.append(ParsedSignal(
                signal_type=m.group(1),
                sender=m.group(2),
                handler_function=m.group(3),
                start_line=start_line,
            ))
        return signals

    def _extract_cron_jobs_regex(self, src: str) -> List[ParsedCronJob]:
        crons = []

        if 'CELERY_BEAT_SCHEDULE' in src or 'beat_schedule' in src:
            pattern = r'''['"]([\w\-\.]+)['"]\s*:\s*\{[^}]*?['"]task['"]\s*:\s*['"]([\w\.]+)['"]'''
            for m in re.finditer(pattern, src, re.DOTALL):
                crons.append(ParsedCronJob(
                    task_name=m.group(2),
                    schedule=m.group(1),
                    start_line=src[:m.start()].count('\n') + 1,
                ))

        # @periodic_task or @shared_task decorators
        dec_pattern = re.compile(
            r'@(periodic_task|shared_task)\s*\([^)]*run_every[^)]*\)\s*\n\s*def\s+(\w+)',
            re.MULTILINE,
        )
        for m in dec_pattern.finditer(src):
            start_line = src[:m.start()].count('\n') + 1
            crons.append(ParsedCronJob(
                task_name=m.group(2),
                schedule=m.group(0).split('\n')[0],
                start_line=start_line,
            ))

        return crons
