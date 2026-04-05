# CodeVault

**Codebase Intelligence System** — parse projects in Python, JavaScript/TypeScript, Go, Rust, and Java. Build a knowledge graph (Neo4j) + vector store (ChromaDB). Query your codebase via REST API or MCP server. Connect to Claude Desktop, Cursor, or any AI coding assistant.

## Supported Languages

| Language | Parser | Entities Extracted |
|----------|--------|--------------------|
| Python | Tree-sitter + regex | Functions, classes, Django models, URL endpoints, signals, Celery crons |
| JavaScript/TypeScript | Regex | Functions, arrow functions, classes, Express/Next.js routes, JSDoc |
| Go | Regex | Functions, methods, structs, interfaces, net/http/Gin/Echo routes |
| Rust | Regex | Functions, structs, traits, enums, Actix/Axum routes |
| Java | Regex | Classes, methods, interfaces, Spring MVC/Boot endpoints, annotations |

## Quick Start (60 seconds)

```bash
git clone https://github.com/yourname/codevault && cd codevault
./scripts/setup.sh                           # Start all services
./scripts/mcp_quickstart.sh you@email.com password123 my-project /path/to/code
# Done! Follow the output to configure Claude Desktop.
```

## Architecture

```
Django REST API  ──→  Celery Workers  ──→  Parser (Tree-sitter)
                                            ├── Neo4j  (structural graph)
                                            └── ChromaDB (vector embeddings)

MCP Server (stdio / SSE)  ──→  REST API  ──→  Graph + Vector + LLM
```

**Stack:** Django 5, DRF, SimpleJWT, Celery + Redis, Neo4j 5, ChromaDB, Tree-sitter, OpenAI / Anthropic / Google Gemini

---

## Quick Start with Docker

### Prerequisites

- Docker + Docker Compose
- An LLM API key (OpenAI, Anthropic, or Google)

### 1. Clone and configure

```bash
git clone https://github.com/yourname/codevault
cd codevault
cp .env.example .env
```

Edit `.env` and set at minimum:

```
SECRET_KEY=your-secret-key-here
OPENAI_API_KEY=sk-...   # or ANTHROPIC_API_KEY / GOOGLE_API_KEY
```

### 2. Start services

```bash
docker compose up -d
```

This starts: PostgreSQL, Redis, Neo4j, the Django web server, Celery worker, and Celery Beat scheduler.

### 3. Create a superuser

```bash
docker compose exec web python manage.py createsuperuser
```

### 4. Register and get a JWT token

```bash
curl -X POST http://localhost:8000/api/auth/register/ \
  -H "Content-Type: application/json" \
  -d '{"email": "you@example.com", "name": "Your Name", "password": "secret123", "password_confirm": "secret123"}'
```

Response includes `access` and `refresh` tokens.

---

## Local Development Setup

### Prerequisites

- Python 3.11+
- PostgreSQL 14+
- Redis 7+
- Neo4j 5.x (or use Docker for just Neo4j)

### 1. Install dependencies

```bash
python -m venv venv
source venv/bin/activate   # Windows: venv\Scripts\activate
pip install -r requirements.txt
```

### 2. Configure environment

```bash
cp .env.example .env
# Edit .env with your database, Redis, Neo4j credentials
```

### 3. Run migrations

```bash
python manage.py migrate
python manage.py createsuperuser
```

### 4. Start development server

```bash
python manage.py runserver
```

### 5. Start Celery worker (separate terminal)

```bash
celery -A codevault worker -l info
```

### 6. (Optional) Start Celery Beat for scheduled tasks

```bash
celery -A codevault beat -l info --scheduler django_celery_beat.schedulers:DatabaseScheduler
```

---

## Ingesting a Project

### Option A: Management command

```bash
# Queue via Celery (default)
python manage.py ingest_local my-project /path/to/your/django/project

# Run synchronously
python manage.py ingest_local my-project /path/to/project --sync

# Clear existing data first
python manage.py ingest_local my-project /path/to/project --sync --clear
```

### Option B: REST API

```bash
# First create the project
curl -X POST http://localhost:8000/api/projects/ \
  -H "Authorization: Bearer <ACCESS_TOKEN>" \
  -H "Content-Type: application/json" \
  -d '{
    "name": "My Django App",
    "description": "Our main application",
    "local_path": "/path/to/your/project"
  }'

# Then trigger ingestion
curl -X POST http://localhost:8000/api/projects/my-django-app/ingest/ \
  -H "Authorization: Bearer <ACCESS_TOKEN>" \
  -H "Content-Type: application/json" \
  -d '{"path": "/path/to/your/project", "sync": false}'
```

---

## API Reference

All API endpoints require `Authorization: Bearer <JWT_TOKEN>` unless marked as public.

### Authentication

| Method | Endpoint | Description |
|--------|----------|-------------|
| POST | `/api/auth/register/` | Register new user |
| POST | `/api/auth/login/` | Login, get JWT tokens |
| POST | `/api/auth/refresh/` | Refresh access token |
| POST | `/api/auth/logout/` | Revoke refresh token |
| GET/PATCH | `/api/auth/profile/` | Get or update profile |
| POST | `/api/auth/change-password/` | Change password |
| GET/POST | `/api/auth/tokens/` | List or create API tokens |
| DELETE | `/api/auth/tokens/<id>/` | Revoke API token |

#### Register

```bash
curl -X POST http://localhost:8000/api/auth/register/ \
  -H "Content-Type: application/json" \
  -d '{"email": "user@example.com", "name": "Alice", "password": "secret123", "password_confirm": "secret123"}'
```

#### Login

```bash
curl -X POST http://localhost:8000/api/auth/login/ \
  -H "Content-Type: application/json" \
  -d '{"email": "user@example.com", "password": "secret123"}'
```

---

### Projects

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/api/projects/` | List your projects |
| POST | `/api/projects/` | Create a project |
| GET | `/api/projects/<slug>/` | Get project details |
| PATCH | `/api/projects/<slug>/` | Update project |
| DELETE | `/api/projects/<slug>/` | Delete project |
| GET | `/api/projects/<slug>/members/` | List members |
| POST | `/api/projects/<slug>/members/` | Add member |
| PATCH | `/api/projects/<slug>/members/<id>/` | Update member role |
| DELETE | `/api/projects/<slug>/members/<id>/` | Remove member |

#### Create Project

```bash
curl -X POST http://localhost:8000/api/projects/ \
  -H "Authorization: Bearer <TOKEN>" \
  -H "Content-Type: application/json" \
  -d '{
    "name": "My App",
    "description": "Main Django app",
    "repo_url": "https://github.com/org/repo",
    "local_path": "/srv/my-app"
  }'
```

---

### Intelligence / Graph

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/api/projects/<slug>/stats/` | Graph + vector statistics |
| GET | `/api/projects/<slug>/files/` | List indexed files |
| GET | `/api/projects/<slug>/functions/` | Search/list functions |
| GET | `/api/projects/<slug>/endpoints/` | List API endpoints |
| GET | `/api/projects/<slug>/models/` | List Django models |
| POST | `/api/projects/<slug>/query/` | LLM query |
| GET | `/api/projects/<slug>/query-logs/` | Query history |
| POST | `/api/projects/<slug>/ingest/` | Trigger ingestion |
| GET | `/api/projects/<slug>/jobs/` | List ingestion jobs |

#### Get Project Stats

```bash
curl http://localhost:8000/api/projects/my-app/stats/ \
  -H "Authorization: Bearer <TOKEN>"
```

```json
{
  "files": 42,
  "functions": 318,
  "classes": 45,
  "endpoints": 23,
  "signals": 5,
  "cron_jobs": 3,
  "vector_embeddings": 363
}
```

#### Search Functions

```bash
curl "http://localhost:8000/api/projects/my-app/functions/?search=authenticate&limit=5" \
  -H "Authorization: Bearer <TOKEN>"
```

#### List API Endpoints

```bash
curl http://localhost:8000/api/projects/my-app/endpoints/ \
  -H "Authorization: Bearer <TOKEN>"
```

#### Ask a Question (LLM Query)

```bash
curl -X POST http://localhost:8000/api/projects/my-app/query/ \
  -H "Authorization: Bearer <TOKEN>" \
  -H "Content-Type: application/json" \
  -d '{
    "question": "How does user authentication work? Which views are involved?",
    "effort": "medium"
  }'
```

Effort levels:
- `low` — Fast semantic search only (gpt-4o-mini / gemini-flash / claude-haiku)
- `medium` — Semantic + 1-hop graph expansion (gpt-4o / gemini-pro / claude-sonnet)
- `high` — Full multi-hop graph traversal + models/endpoints context (gpt-4o / claude-opus)

#### Trigger Ingestion

```bash
curl -X POST http://localhost:8000/api/projects/my-app/ingest/ \
  -H "Authorization: Bearer <TOKEN>" \
  -H "Content-Type: application/json" \
  -d '{"path": "/srv/my-app", "sync": false, "clear": false}'
```

---

### GitHub Webhook

| Method | Endpoint | Description |
|--------|----------|-------------|
| POST | `/api/webhooks/github/<slug>/` | GitHub push event receiver |

#### Setup

1. Set `github_webhook_secret` on your project (via PATCH `/api/projects/<slug>/`)
2. In your GitHub repo: **Settings → Webhooks → Add webhook**
   - Payload URL: `https://your-codevault.example.com/api/webhooks/github/my-app/`
   - Content type: `application/json`
   - Secret: your `github_webhook_secret` value
   - Events: **Push**

On each push, CodeVault will automatically re-index only the changed Python files.

---

## MCP Server — Claude Desktop

Add this to your Claude Desktop config (`~/Library/Application Support/Claude/claude_desktop_config.json` on macOS):

```json
{
  "mcpServers": {
    "codevault": {
      "command": "python",
      "args": [
        "-m", "apps.mcp.server",
        "--api-url", "http://localhost:8000",
        "--api-token", "YOUR_JWT_ACCESS_TOKEN"
      ],
      "cwd": "/path/to/codevault"
    }
  }
}
```

**Getting a token:**

```bash
curl -X POST http://localhost:8000/api/auth/login/ \
  -H "Content-Type: application/json" \
  -d '{"email": "you@example.com", "password": "secret123"}' \
  | python3 -c "import sys,json; print(json.load(sys.stdin)['access'])"
```

Or create a long-lived API token:

```bash
curl -X POST http://localhost:8000/api/auth/tokens/ \
  -H "Authorization: Bearer <JWT_TOKEN>" \
  -H "Content-Type: application/json" \
  -d '{"name": "Claude Desktop"}'
```

Use the `token` value from the response in your MCP config.

---

## MCP Server — Cursor

Cursor supports MCP over HTTP+SSE. Add to your Cursor settings:

```json
{
  "mcpServers": {
    "codevault": {
      "url": "http://localhost:8000/mcp/sse/",
      "headers": {
        "Authorization": "Bearer YOUR_JWT_ACCESS_TOKEN"
      }
    }
  }
}
```

Alternatively, use the stdio transport (same as Claude Desktop) if Cursor supports it.

---

## Available MCP Tools

| Tool | Description |
|------|-------------|
| `search_codebase` | Semantic search for functions/classes by description |
| `get_function` | Full details of a function: code, endpoint trigger, signals |
| `list_api_endpoints` | All REST endpoints with URL patterns and handlers |
| `list_django_models` | All Django ORM models with base classes |
| `ask_codebase` | LLM-synthesized answer with effort tiers |
| `get_project_stats` | Files, functions, classes, endpoints count |
| `list_files` | All indexed files with entity counts |

### Example MCP Queries (Claude Desktop)

Once connected, you can ask Claude:

> "Using codevault, search for authentication-related functions in my-app"

> "What API endpoints does my-app expose and what do they do?"

> "Ask the codebase: how does the payment processing flow work?"

---

## Project Structure

```
codevault/
├── manage.py
├── requirements.txt
├── .env.example
├── Dockerfile
├── docker-compose.yml
│
├── codevault/              Django project settings
│   ├── settings.py
│   ├── urls.py
│   ├── celery.py
│   └── wsgi.py / asgi.py
│
└── apps/
    ├── accounts/           JWT auth, custom User, API tokens
    ├── projects/           Multi-project management, members
    ├── intelligence/       Core intelligence engine
    │   └── services/
    │       ├── parser.py   Tree-sitter AST parser
    │       ├── graph.py    Neo4j service
    │       ├── vector.py   ChromaDB service
    │       ├── ingestion.py Orchestrator
    │       └── llm.py      Multi-provider LLM with effort tiers
    ├── api/                REST API views, webhooks
    └── mcp/                MCP server (stdio + HTTP/SSE)
```

---

## Environment Variables Reference

| Variable | Default | Description |
|----------|---------|-------------|
| `SECRET_KEY` | (required) | Django secret key |
| `DEBUG` | `True` | Debug mode |
| `ALLOWED_HOSTS` | `localhost,127.0.0.1` | Allowed hostnames |
| `DATABASE_URL` | PostgreSQL local | Database connection string |
| `REDIS_URL` | `redis://localhost:6379/0` | Redis for Celery broker |
| `NEO4J_URI` | `bolt://localhost:7687` | Neo4j Bolt URL |
| `NEO4J_USER` | `neo4j` | Neo4j username |
| `NEO4J_PASSWORD` | (required) | Neo4j password |
| `CHROMA_DB_PATH` | `./chroma_db_data` | ChromaDB persistence directory |
| `OPENAI_API_KEY` | — | OpenAI key (priority 1) |
| `ANTHROPIC_API_KEY` | — | Anthropic key (priority 2) |
| `GOOGLE_API_KEY` | — | Google Gemini key (priority 3) |
| `CORS_ALLOW_ALL_ORIGINS` | `True` | Allow all CORS origins |

---

## Admin Interface

Available at `http://localhost:8000/admin/` after creating a superuser.

Includes admin panels for: Users, API Tokens, Projects, Project Members, Indexed Files, Ingestion Jobs, and Query Logs.

---

## Development Notes

### Running tests

```bash
python manage.py test apps
```

### Checking Celery task status

```bash
celery -A codevault inspect active
celery -A codevault inspect stats
```

### Neo4j Browser

Visit `http://localhost:7474` (Docker default credentials: `neo4j` / `codevault_pass`).

Try this Cypher to explore the graph:
```cypher
MATCH (n {namespace: 'my-project-slug'}) RETURN n LIMIT 50
```

### Resetting a project's index

```bash
python manage.py ingest_local my-project /path --sync --clear
```
