# CLAUDE.md — CodeVault AI Context

> This file provides context for AI assistants working on this codebase.
> It is read by Claude Code, Cursor, Copilot, and other AI-powered development tools.

Testing the github webhook integration

## Project Overview

CodeVault is a **Codebase Intelligence System** that parses source code projects, builds a knowledge graph (Neo4j) + vector store (ChromaDB), and lets you query your codebase via REST API or MCP server. It supports Python, JavaScript/TypeScript, Go, Rust, and Java.

**Primary use case:** Connect this as an MCP service to AI agents (Claude Desktop, Cursor, etc.) so they have deep, structural understanding of any codebase they're helping develop.

## Tech Stack

- **Framework:** Django 5 + Django REST Framework
- **Auth:** SimpleJWT + custom API tokens (HMAC-SHA256)
- **Task Queue:** Celery + Redis
- **Knowledge Graph:** Neo4j 5 (code structure, relationships)
- **Vector Store:** ChromaDB (semantic search via embeddings)
- **Code Parsing:** Tree-sitter (Python) + regex fallback (all languages)
- **LLM Providers:** OpenAI, Anthropic, Google Gemini (effort-tiered)
- **Database:** PostgreSQL 16
- **Container:** Docker Compose (full stack)

## Architecture

```
┌─────────────────────────────────────────────────┐
│                   Clients                        │
│  Claude Desktop (stdio MCP) │ Cursor (SSE MCP)  │
│  REST API clients │ GitHub Webhooks              │
└─────────────┬───────────────┬───────────────────┘
              │               │
┌─────────────▼───────────────▼───────────────────┐
│              Django Application                   │
│                                                   │
│  apps/accounts/    JWT auth, API tokens           │
│  apps/projects/    Multi-project, RBAC            │
│  apps/api/         REST endpoints, webhooks       │
│  apps/mcp/         MCP server (stdio + HTTP/SSE)  │
│  apps/intelligence/                               │
│    └── services/                                  │
│        ├── parser.py      Tree-sitter AST parser  │
│        ├── parsers/       Multi-language registry  │
│        ├── graph.py       Neo4j operations         │
│        ├── vector.py      ChromaDB embeddings      │
│        ├── llm.py         Multi-provider LLM       │
│        └── ingestion.py   Pipeline orchestrator    │
└───────┬──────────┬────────────┬──────────────────┘
        │          │            │
   ┌────▼──┐  ┌───▼────┐  ┌───▼─────┐
   │Neo4j  │  │ChromaDB│  │Celery   │
   │(graph)│  │(vector)│  │+ Redis  │
   └───────┘  └────────┘  └─────────┘
```

## Directory Structure

```
codevault/
├── CLAUDE.md                    ← You are here
├── manage.py                    Django CLI entry point
├── requirements.txt             Python dependencies
├── Dockerfile                   Container build
├── docker-compose.yml           Full stack orchestration
├── .env.example                 Environment template
│
├── codevault/                   Django project config
│   ├── settings.py              All configuration (DB, cache, auth, services)
│   ├── urls.py                  Root URL routing + health checks
│   ├── celery.py                Celery app configuration
│   ├── wsgi.py / asgi.py        WSGI/ASGI entry points
│
├── apps/
│   ├── accounts/                Authentication & user management
│   │   ├── models.py            User (email-based), APIToken
│   │   ├── views.py             Register, login, profile, token CRUD
│   │   ├── serializers.py       DRF serializers for auth flows
│   │   └── urls.py              /api/auth/* routes
│   │
│   ├── projects/                Project management
│   │   ├── models.py            Project, ProjectMember (with RBAC)
│   │   ├── serializers.py       Project CRUD serializers
│   │   └── urls.py              (included via api/urls.py)
│   │
│   ├── intelligence/            Core intelligence engine
│   │   ├── models.py            IndexedFile, IngestionJob, QueryLog
│   │   ├── tasks.py             Celery async tasks
│   │   ├── management/commands/ CLI commands (ingest_local)
│   │   └── services/
│   │       ├── parser.py        Python Tree-sitter parser + dataclasses
│   │       ├── parsers/         Multi-language parser registry
│   │       │   ├── __init__.py  Registry: extension → parser mapping
│   │       │   ├── base.py      Abstract base parser
│   │       │   ├── python_parser.py
│   │       │   ├── javascript_parser.py
│   │       │   ├── go_parser.py
│   │       │   ├── rust_parser.py
│   │       │   └── java_parser.py
│   │       ├── graph.py         Neo4j: nodes, relationships, queries
│   │       ├── vector.py        ChromaDB: embeddings, semantic search
│   │       ├── llm.py           Multi-LLM with effort tiers
│   │       └── ingestion.py     Full pipeline orchestrator
│   │
│   ├── api/                     REST API
│   │   ├── views.py             All intelligence/query endpoints
│   │   ├── serializers.py       Request/response models
│   │   ├── webhooks.py          GitHub webhook handler (HMAC)
│   │   ├── middleware.py        Rate limiting, request timing
│   │   └── urls.py              /api/* route definitions
│   │
│   └── mcp/                     Model Context Protocol server
│       ├── server.py            stdio transport (Claude Desktop)
│       ├── views.py             HTTP + SSE transport (Cursor)
│       ├── tools.py             MCP tool definitions (11 tools)
│       ├── urls.py              /mcp/* routes
│       └── __main__.py          python -m apps.mcp entry point
│
└── tests/                       Test suite
    ├── conftest.py              Shared fixtures
    ├── test_parser.py           Parser service tests
    ├── test_graph.py            Neo4j service tests
    ├── test_vector.py           ChromaDB service tests
    ├── test_ingestion.py        Ingestion pipeline tests
    ├── test_api.py              REST API endpoint tests
    └── test_mcp.py              MCP server tests
```

## Key Design Decisions

1. **Namespace scoping**: Every Neo4j node and ChromaDB collection is scoped by project namespace/slug. This enables multi-tenant isolation without separate databases.

2. **Effort tiers**: LLM queries have three tiers (low/medium/high) that control the tradeoff between speed and depth of context gathering.

3. **Dual MCP transport**: stdio for Claude Desktop (local), HTTP+SSE for Cursor/remote clients. Both share the same tool definitions.

4. **Multi-language via registry**: File extension → parser class mapping. Each parser implements `BaseParser.parse()` returning a `ParsedFile`. Easy to add new languages.

5. **Incremental ingestion**: File hashes (SHA-256) skip unchanged files. GitHub webhooks trigger ingestion of only changed files.

## Important Patterns

### Adding a new MCP tool
1. Define the tool schema in `apps/mcp/tools.py` (TOOLS list)
2. Add handler in `apps/mcp/views.py` → `_execute_tool()`
3. Add proxy method in `apps/mcp/server.py` → dispatch dict + `_tool_*` method
4. Add corresponding REST API endpoint if needed

### Adding a new language parser
1. Create `apps/intelligence/services/parsers/<lang>_parser.py`
2. Extend `BaseParser`, implement `parse()` method
3. Register extension mapping in `parsers/__init__.py` PARSER_REGISTRY
4. Add language to `Project.LANGUAGE_CHOICES` in `apps/projects/models.py`

### Adding a new API endpoint
1. Add view class in `apps/api/views.py`
2. Add URL pattern in `apps/api/urls.py`
3. Add serializer in `apps/api/serializers.py` if needed
4. All views use `get_project_or_403()` for access control

## Common Commands

```bash
# Development
python manage.py runserver                    # Start dev server
celery -A codevault worker -l info            # Start Celery worker
python manage.py ingest_local <slug> <path>   # Ingest a project

# Docker
docker compose up -d                          # Start full stack
docker compose exec web python manage.py migrate
docker compose exec web python manage.py createsuperuser

# MCP Server
python -m apps.mcp.server --api-token <JWT>   # Start stdio MCP server

# Testing
python manage.py test tests                   # Run test suite
```

## Environment Variables

Critical ones (see .env.example for full list):
- `SECRET_KEY` — Django secret (required in production)
- `DATABASE_URL` — PostgreSQL connection string
- `REDIS_URL` — Redis for Celery + caching
- `NEO4J_URI`, `NEO4J_USER`, `NEO4J_PASSWORD` — Neo4j connection
- `CHROMA_DB_PATH` — ChromaDB persistence directory
- `OPENAI_API_KEY` / `ANTHROPIC_API_KEY` / `GOOGLE_API_KEY` — At least one required

## API Authentication

All API endpoints require `Authorization: Bearer <token>`. Two token types:
1. **JWT** — Short-lived (60min), from POST `/api/auth/login/`
2. **API Token** — Long-lived, from POST `/api/auth/tokens/`. Better for MCP servers.

## Neo4j Graph Schema

Node types: `File`, `Function`, `Class`, `DjangoModel`, `APIEndpoint`, `Signal`, `CronJob`
All nodes have a `namespace` property for project scoping.

Relationships:
- `(File)-[:DEFINES]->(Function|Class|APIEndpoint|Signal|CronJob)`
- `(APIEndpoint)-[:TRIGGERS]->(Function)`
- `(Signal)-[:HANDLED_BY]->(Function)`

## Coding Conventions

- Python 3.11+, Django 5 patterns
- Type hints on all service methods
- Logging via `logging.getLogger(__name__)` in every module
- Services are instantiated with project-scoped config (namespace/collection)
- Always close GraphService connections (use context manager or explicit `.close()`)
- Async tasks go in `apps/intelligence/tasks.py`
- Tests use pytest with Django fixtures
