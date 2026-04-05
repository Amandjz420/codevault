"""
Tests for the code parser service (Python + multi-language).
"""
import pytest
from apps.intelligence.services.parser import CodeParser, ParsedFile
from tests.conftest import (
    PYTHON_SOURCE, JS_SOURCE, GO_SOURCE, RUST_SOURCE, JAVA_SOURCE,
)


class TestPythonParser:
    """Test the Python Tree-sitter/regex parser."""

    def setup_method(self):
        self.parser = CodeParser()

    def test_parse_returns_parsed_file(self):
        result = self.parser.parse_file(PYTHON_SOURCE, 'test.py')
        assert isinstance(result, ParsedFile)

    def test_extracts_imports(self):
        result = self.parser.parse_file(PYTHON_SOURCE, 'test.py')
        assert len(result.imports) >= 3
        import_text = ' '.join(result.imports)
        assert 'import os' in import_text
        assert 'from django.db import models' in import_text

    def test_extracts_classes(self):
        result = self.parser.parse_file(PYTHON_SOURCE, 'test.py')
        assert len(result.classes) >= 1
        profile_cls = next(c for c in result.classes if c.name == 'UserProfile')
        assert profile_cls.is_django_model is True
        assert any('Model' in b for b in profile_cls.bases)

    def test_extracts_model_fields(self):
        result = self.parser.parse_file(PYTHON_SOURCE, 'test.py')
        profile_cls = next(c for c in result.classes if c.name == 'UserProfile')
        field_names = [f['name'] for f in profile_cls.fields]
        assert 'user' in field_names or 'bio' in field_names

    def test_extracts_functions(self):
        result = self.parser.parse_file(PYTHON_SOURCE, 'test.py')
        func_names = [f.name for f in result.functions]
        assert 'create_default_profile' in func_names
        assert 'auto_create_profile' in func_names

    def test_extracts_methods(self):
        result = self.parser.parse_file(PYTHON_SOURCE, 'test.py')
        methods = [f for f in result.functions if f.is_method]
        method_names = [m.name for m in methods]
        assert 'get_display_name' in method_names

    def test_detects_async_functions(self):
        result = self.parser.parse_file(PYTHON_SOURCE, 'test.py')
        async_funcs = [f for f in result.functions if f.is_async]
        assert any(f.name == 'fetch_avatar' for f in async_funcs)

    def test_extracts_signals(self):
        result = self.parser.parse_file(PYTHON_SOURCE, 'test.py')
        assert len(result.signals) >= 1
        sig = result.signals[0]
        assert 'post_save' in sig.signal_type
        assert sig.handler_function == 'auto_create_profile'

    def test_extracts_docstrings(self):
        result = self.parser.parse_file(PYTHON_SOURCE, 'test.py')
        profile_cls = next(c for c in result.classes if c.name == 'UserProfile')
        assert profile_cls.docstring is not None
        assert 'User profile' in profile_cls.docstring

    def test_parent_class_detection(self):
        result = self.parser.parse_file(PYTHON_SOURCE, 'test.py')
        method = next(f for f in result.functions if f.name == 'get_display_name')
        assert method.parent_class == 'UserProfile'

    def test_empty_file(self):
        result = self.parser.parse_file(b'', 'empty.py')
        assert result.functions == []
        assert result.classes == []

    def test_syntax_error_resilient(self):
        bad_source = b'def broken(\n  class Hmm\nimport'
        result = self.parser.parse_file(bad_source, 'bad.py')
        assert isinstance(result, ParsedFile)


class TestJavaScriptParser:
    """Test the JavaScript/TypeScript parser."""

    def setup_method(self):
        from apps.intelligence.services.parsers.javascript_parser import JavaScriptParser
        self.parser = JavaScriptParser()

    def test_parse_returns_parsed_file(self):
        result = self.parser.parse(JS_SOURCE, 'app.js')
        assert isinstance(result, ParsedFile)
        assert result.language == 'javascript'

    def test_extracts_imports(self):
        result = self.parser.parse(JS_SOURCE, 'app.js')
        assert len(result.imports) >= 1

    def test_extracts_functions(self):
        result = self.parser.parse(JS_SOURCE, 'app.js')
        func_names = [f.name for f in result.functions]
        assert 'getUserById' in func_names

    def test_extracts_arrow_functions(self):
        result = self.parser.parse(JS_SOURCE, 'app.js')
        func_names = [f.name for f in result.functions]
        assert 'createUser' in func_names

    def test_extracts_classes(self):
        result = self.parser.parse(JS_SOURCE, 'app.js')
        class_names = [c.name for c in result.classes]
        assert 'AuthController' in class_names

    def test_extracts_express_routes(self):
        result = self.parser.parse(JS_SOURCE, 'app.js')
        assert len(result.endpoints) >= 2
        urls = [e.url_pattern for e in result.endpoints]
        assert '/users/:id' in urls
        assert '/users' in urls

    def test_detects_async(self):
        result = self.parser.parse(JS_SOURCE, 'app.js')
        async_funcs = [f for f in result.functions if f.is_async]
        assert len(async_funcs) >= 1

    def test_typescript_language_detection(self):
        result = self.parser.parse(JS_SOURCE, 'app.tsx')
        assert result.language == 'typescript'


class TestGoParser:
    """Test the Go parser."""

    def setup_method(self):
        from apps.intelligence.services.parsers.go_parser import GoParser
        self.parser = GoParser()

    def test_parse_returns_parsed_file(self):
        result = self.parser.parse(GO_SOURCE, 'handler.go')
        assert isinstance(result, ParsedFile)
        assert result.language == 'go'

    def test_extracts_functions(self):
        result = self.parser.parse(GO_SOURCE, 'handler.go')
        func_names = [f.name for f in result.functions]
        assert 'CreateUser' in func_names

    def test_extracts_methods_with_receiver(self):
        result = self.parser.parse(GO_SOURCE, 'handler.go')
        methods = [f for f in result.functions if f.is_method]
        assert any(f.name == 'GetUser' for f in methods)
        get_user = next(f for f in methods if f.name == 'GetUser')
        assert get_user.parent_class == 'UserHandler'

    def test_extracts_structs(self):
        result = self.parser.parse(GO_SOURCE, 'handler.go')
        class_names = [c.name for c in result.classes]
        assert 'UserHandler' in class_names
        assert 'User' in class_names

    def test_extracts_struct_fields(self):
        result = self.parser.parse(GO_SOURCE, 'handler.go')
        user = next(c for c in result.classes if c.name == 'User')
        field_names = [f['name'] for f in user.fields]
        assert any(n in field_names for n in ['ID', 'Name', 'Email'])

    def test_extracts_doc_comments(self):
        result = self.parser.parse(GO_SOURCE, 'handler.go')
        get_user = next((f for f in result.functions if f.name == 'GetUser'), None)
        assert get_user is not None
        assert get_user.docstring is not None
        assert 'retrieves' in get_user.docstring.lower()

    def test_extracts_imports(self):
        result = self.parser.parse(GO_SOURCE, 'handler.go')
        assert len(result.imports) >= 1


class TestRustParser:
    """Test the Rust parser."""

    def setup_method(self):
        from apps.intelligence.services.parsers.rust_parser import RustParser
        self.parser = RustParser()

    def test_parse_returns_parsed_file(self):
        result = self.parser.parse(RUST_SOURCE, 'main.rs')
        assert isinstance(result, ParsedFile)
        assert result.language == 'rust'

    def test_extracts_functions(self):
        result = self.parser.parse(RUST_SOURCE, 'main.rs')
        func_names = [f.name for f in result.functions]
        assert 'get_user' in func_names
        assert 'create_user' in func_names

    def test_extracts_impl_methods(self):
        result = self.parser.parse(RUST_SOURCE, 'main.rs')
        methods = [f for f in result.functions if f.is_method]
        assert any(f.name == 'new' for f in methods)

    def test_extracts_structs(self):
        result = self.parser.parse(RUST_SOURCE, 'main.rs')
        class_names = [c.name for c in result.classes]
        assert 'User' in class_names

    def test_extracts_traits(self):
        result = self.parser.parse(RUST_SOURCE, 'main.rs')
        trait_names = [c.name for c in result.classes if 'trait' in c.bases]
        assert 'UserRepository' in trait_names

    def test_extracts_actix_routes(self):
        result = self.parser.parse(RUST_SOURCE, 'main.rs')
        assert len(result.endpoints) >= 2
        urls = [e.url_pattern for e in result.endpoints]
        assert '/users/{id}' in urls
        assert '/users' in urls

    def test_extracts_derive_decorators(self):
        result = self.parser.parse(RUST_SOURCE, 'main.rs')
        user = next((c for c in result.classes if c.name == 'User'), None)
        assert user is not None


class TestJavaParser:
    """Test the Java parser."""

    def setup_method(self):
        from apps.intelligence.services.parsers.java_parser import JavaParser
        self.parser = JavaParser()

    def test_parse_returns_parsed_file(self):
        result = self.parser.parse(JAVA_SOURCE, 'UserController.java')
        assert isinstance(result, ParsedFile)
        assert result.language == 'java'

    def test_extracts_classes(self):
        result = self.parser.parse(JAVA_SOURCE, 'UserController.java')
        class_names = [c.name for c in result.classes]
        assert 'UserController' in class_names

    def test_extracts_interfaces(self):
        result = self.parser.parse(JAVA_SOURCE, 'UserController.java')
        class_names = [c.name for c in result.classes]
        assert 'UserRepository' in class_names

    def test_extracts_methods(self):
        result = self.parser.parse(JAVA_SOURCE, 'UserController.java')
        func_names = [f.name for f in result.functions]
        assert 'getUser' in func_names
        assert 'createUser' in func_names

    def test_extracts_spring_endpoints(self):
        result = self.parser.parse(JAVA_SOURCE, 'UserController.java')
        assert len(result.endpoints) >= 2
        methods = [e.http_methods[0] for e in result.endpoints]
        assert 'GET' in methods
        assert 'POST' in methods

    def test_extracts_imports(self):
        result = self.parser.parse(JAVA_SOURCE, 'UserController.java')
        assert len(result.imports) >= 1

    def test_extracts_spring_url_patterns(self):
        result = self.parser.parse(JAVA_SOURCE, 'UserController.java')
        urls = [e.url_pattern for e in result.endpoints]
        assert any('/api/users' in u for u in urls)


class TestParserRegistry:
    """Test the multi-language parser registry."""

    def test_python_extension(self):
        from apps.intelligence.services.parsers import get_parser_for_file
        parser = get_parser_for_file('test.py')
        assert parser is not None
        assert parser.language == 'python'

    def test_javascript_extension(self):
        from apps.intelligence.services.parsers import get_parser_for_file
        parser = get_parser_for_file('app.js')
        assert parser is not None
        assert parser.language == 'javascript'

    def test_typescript_extension(self):
        from apps.intelligence.services.parsers import get_parser_for_file
        for ext in ['.ts', '.tsx', '.jsx']:
            parser = get_parser_for_file(f'file{ext}')
            assert parser is not None

    def test_go_extension(self):
        from apps.intelligence.services.parsers import get_parser_for_file
        parser = get_parser_for_file('main.go')
        assert parser is not None
        assert parser.language == 'go'

    def test_rust_extension(self):
        from apps.intelligence.services.parsers import get_parser_for_file
        parser = get_parser_for_file('lib.rs')
        assert parser is not None
        assert parser.language == 'rust'

    def test_java_extension(self):
        from apps.intelligence.services.parsers import get_parser_for_file
        parser = get_parser_for_file('App.java')
        assert parser is not None
        assert parser.language == 'java'

    def test_unsupported_extension(self):
        from apps.intelligence.services.parsers import get_parser_for_file
        parser = get_parser_for_file('style.css')
        assert parser is None

    def test_supported_extensions_set(self):
        from apps.intelligence.services.parsers import SUPPORTED_EXTENSIONS
        assert '.py' in SUPPORTED_EXTENSIONS
        assert '.js' in SUPPORTED_EXTENSIONS
        assert '.go' in SUPPORTED_EXTENSIONS
        assert '.rs' in SUPPORTED_EXTENSIONS
        assert '.java' in SUPPORTED_EXTENSIONS
