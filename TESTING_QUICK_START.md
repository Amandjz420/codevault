# Testing Quick Start Guide

## Installation

```bash
# Install test dependencies
pip install -r requirements.txt
```

## Running Tests

### All tests
```bash
pytest tests/
```

### Specific test file
```bash
pytest tests/test_models.py -v
pytest tests/test_api.py -v
```

### Specific test class
```bash
pytest tests/test_models.py::TestUserModel -v
```

### Specific test method
```bash
pytest tests/test_models.py::TestUserModel::test_create_user -v
```

### With coverage report
```bash
pytest --cov=apps --cov-report=html
# Open htmlcov/index.html to view
```

### Verbose output (see print statements)
```bash
pytest -s tests/test_models.py::TestUserModel::test_create_user
```

### Run tests in parallel (faster)
```bash
pip install pytest-xdist
pytest -n auto
```

### Stop on first failure
```bash
pytest -x tests/
```

## Test Organization

```
tests/
├── conftest.py              # Shared fixtures
├── test_models.py           # ORM models (40+ tests)
├── test_parser.py           # Code parsers (70+ tests)
├── test_api.py              # REST API (50+ tests)
├── test_mcp.py              # MCP tools (50+ tests)
├── test_services.py         # Services (40+ tests)
├── test_middleware.py       # Auth & middleware (35+ tests)
├── test_integration.py      # Integration tests (30+ tests)
└── README.md                # Detailed documentation
```

## Key Test Fixtures

Available in all tests:

```python
def test_example(api_client, user, auth_client, project, project_with_member):
    # api_client - Unauthenticated APIClient
    # user - Test user (test@example.com)
    # auth_client - Authenticated APIClient
    # project - Project owned by test user
    # project_with_member - Project with additional member
    pass
```

## Sample Source Code Fixtures

For parser testing:
- `PYTHON_SOURCE` - Django model example
- `JS_SOURCE` - Express.js routes
- `GO_SOURCE` - Go HTTP handlers
- `RUST_SOURCE` - Actix-web routes
- `JAVA_SOURCE` - Spring REST controller

## Common Test Commands

### Run all tests with output
```bash
pytest -v tests/
```

### Run tests matching a pattern
```bash
pytest -k "auth" -v          # All auth-related tests
pytest -k "test_create" -v   # All create tests
```

### Run tests by marker
```bash
pytest -m auth -v            # Auth tests
pytest -m api -v             # API tests
pytest -m "not slow" -v      # Skip slow tests
```

### Show local variables on failure
```bash
pytest -l tests/
```

### Drop into debugger on failure
```bash
pytest --pdb tests/
```

### Show slowest tests
```bash
pytest --durations=10 tests/
```

## Test Coverage

### Check coverage for specific module
```bash
pytest --cov=apps.models tests/test_models.py
```

### Coverage by file
```bash
pytest --cov=apps --cov-report=term-missing
```

### HTML coverage report
```bash
pytest --cov=apps --cov-report=html
open htmlcov/index.html
```

## Expected Test Results

- **Total tests**: 190+
- **Total test methods**: 190+
- **Total lines of test code**: 2,275+
- **Expected pass rate**: 95%+ (some tests may need service mocks)

## Test Files Summary

| File | Tests | Focus |
|------|-------|-------|
| test_models.py | 36+ | Django ORM models |
| test_parser.py | 49+ | Multi-language parsing |
| test_api.py | 25+ | REST API endpoints |
| test_mcp.py | 30+ | MCP tool validation |
| test_services.py | 21+ | Service layer logic |
| test_middleware.py | 15+ | Auth & middleware |
| test_integration.py | 15+ | End-to-end workflows |

## Debugging Tips

### See what's being tested
```bash
pytest --collect-only tests/
```

### Run single test with debug output
```bash
pytest -s -vv tests/test_models.py::TestUserModel::test_create_user
```

### Print during tests
```python
def test_example(user):
    print(f"User: {user.email}")
    assert True
# Run with: pytest -s tests/
```

### Check database state
```python
def test_example(user):
    from apps.accounts.models import User
    count = User.objects.count()
    print(f"Users in DB: {count}")
    assert count >= 1
```

## CI/CD Integration

Tests are ready for:
- GitHub Actions
- GitLab CI
- Jenkins
- CircleCI
- TravisCI

Basic GitHub Actions example:
```yaml
- name: Run tests
  run: pytest --cov=apps tests/
```

## Troubleshooting

### Tests won't run
```bash
# Install dependencies
pip install -r requirements.txt

# Check Django settings
export DJANGO_SETTINGS_MODULE=codevault.settings
pytest tests/
```

### Database errors
```bash
# Tests use temporary databases, this is normal
# If persisting, check DATABASE settings in codevault/settings.py
```

### Import errors
```bash
# Ensure you're in the project root
cd /sessions/practical-quirky-darwin/mnt/codevault

# Check PYTHONPATH
export PYTHONPATH=$PWD:$PYTHONPATH
pytest tests/
```

### Slow tests
```bash
# Run in parallel
pip install pytest-xdist
pytest -n auto tests/

# Check which tests are slow
pytest --durations=20 tests/
```

## Next Steps

1. Review test documentation: `tests/README.md`
2. Run all tests: `pytest tests/`
3. Check coverage: `pytest --cov=apps tests/`
4. Add new tests as features are developed
5. Integrate into CI/CD pipeline

For detailed information, see `TEST_SUITE_SUMMARY.md`
