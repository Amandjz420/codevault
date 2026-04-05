# CodeVault Test Suite

Comprehensive test suite for the CodeVault Django application.

## Test Organization

### Core Test Modules

- **test_models.py** - Django ORM model tests
  - User authentication and API token handling
  - Project and membership models
  - Ingestion job tracking
  - Query logging
  - Indexed file tracking

- **test_parser.py** - Code parser tests
  - Python parser (Tree-sitter + regex fallback)
  - JavaScript/TypeScript parser
  - Go parser
  - Rust parser
  - Java parser
  - Parser registry and language detection

- **test_api.py** - REST API endpoint tests
  - Authentication (register, login, JWT)
  - Project CRUD operations
  - Member management
  - Ingestion triggering
  - Query API
  - Health checks
  - Rate limiting

- **test_mcp.py** - MCP tool definitions and protocol
  - Tool schema validation
  - Required fields verification
  - Input schema compliance
  - Tool description quality
  - JSON-RPC protocol compliance

- **test_services.py** - Core service layer tests
  - Graph service (Neo4j)
  - Vector service (ChromaDB)
  - LLM query service
  - Ingestion orchestrator
  - Data flow and caching

- **test_middleware.py** - Middleware and authentication
  - API token authentication
  - JWT authentication
  - Permission checking
  - GitHub webhook signature validation
  - CORS handling
  - Rate limiting

## Running Tests

### Install test dependencies

```bash
pip install -r requirements.txt
```

### Run all tests

```bash
pytest
```

### Run specific test module

```bash
pytest tests/test_models.py -v
pytest tests/test_parser.py -v
pytest tests/test_api.py -v
```

### Run tests with coverage

```bash
pytest --cov=apps --cov-report=html
```

### Run tests by marker

```bash
# Auth-related tests
pytest -m auth -v

# API endpoint tests
pytest -m api -v

# Unit tests only (fast)
pytest -m unit -v

# Skip slow tests
pytest -m "not slow" -v
```

### Run tests in parallel (faster)

```bash
pip install pytest-xdist
pytest -n auto
```

## Test Fixtures

All tests use shared fixtures defined in `conftest.py`:

- **api_client** - Unauthenticated API client
- **user** - Test user with email 'test@example.com'
- **auth_client** - Authenticated API client
- **project** - Test project owned by test user
- **project_with_member** - Project with an additional team member

Sample source code fixtures for parser testing:
- **PYTHON_SOURCE** - Django model example
- **JS_SOURCE** - Express.js routes example
- **GO_SOURCE** - Go HTTP handlers example
- **RUST_SOURCE** - Actix-web handlers example
- **JAVA_SOURCE** - Spring REST controller example

## Test Coverage Goals

### By Component

- **Models**: ~95% - All fields, properties, relationships, validation
- **Parsers**: ~85% - Multi-language support, edge cases, error handling
- **API Views**: ~80% - CRUD operations, permissions, error responses
- **Services**: ~75% - Core logic, mocking external services
- **Middleware**: ~85% - Auth, permissions, rate limiting
- **MCP Tools**: ~90% - Schema validation, tool definitions

### By Functionality

- Authentication & Authorization: 15+ tests
- Project Management: 20+ tests
- Code Parsing: 40+ tests
- API Endpoints: 35+ tests
- Service Layer: 25+ tests
- Middleware: 20+ tests

## Writing New Tests

### Test Structure

```python
@pytest.mark.django_db
class TestFeatureName:
    """Test description."""

    def setup_method(self):
        """Setup for each test method."""
        pass

    def test_specific_behavior(self, fixture):
        """Test a specific behavior."""
        assert result == expected
```

### Best Practices

1. **Use descriptive names** - Test names should clearly state what is being tested
2. **One assertion per test** - Aim for single-responsibility tests
3. **Use fixtures** - Leverage conftest.py fixtures for common setup
4. **Mock external services** - Don't make real API calls to OpenAI, Neo4j, etc.
5. **Test both success and failure** - Include error cases
6. **Use parametrize for variations** - Test multiple similar cases efficiently

### Example Test

```python
@pytest.mark.django_db
def test_user_can_create_project(auth_client, user):
    """Test that authenticated users can create projects."""
    response = auth_client.post('/api/projects/', {
        'name': 'New Project',
        'language': 'python',
    }, format='json')
    assert response.status_code == status.HTTP_201_CREATED
    assert response.data['owner'] == user.id
```

## Continuous Integration

The test suite is designed to run in CI environments:

- All tests use `@pytest.mark.django_db` for database access
- External services are mocked (no real API calls)
- Tests are independent and can run in any order
- No hardcoded file paths or environment assumptions

## Debugging Failed Tests

### Print debug output

```bash
pytest -s tests/test_file.py::TestClass::test_method
```

### Drop into debugger

```python
import pdb; pdb.set_trace()
```

### Show full diffs

```bash
pytest -vv tests/test_file.py
```

### Run single test

```bash
pytest tests/test_file.py::TestClass::test_method -v
```
