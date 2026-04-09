# CodeVault — PRD

## Original Problem Statement
Codebase Intelligence System that parses projects in Python, JavaScript/TypeScript, Go, Rust, and Java. Builds a knowledge graph (Neo4j) + vector store (ChromaDB). Queries the codebase via REST API or MCP server.

## Architecture
- **Backend**: Django 5 + DRF + SimpleJWT
- **Queue**: Celery + Redis
- **Graph DB**: Neo4j 5
- **Vector DB**: ChromaDB
- **Parser**: Tree-sitter (AST-based)
- **LLMs**: OpenAI / Anthropic / Google Gemini (multi-provider, 3 effort tiers)

## Apps
| App | Purpose |
|-----|---------|
| accounts | JWT auth, custom User, API tokens |
| projects | Multi-project management, team members |
| intelligence | Core engine — parsing, graph, vector, LLM |
| api | REST API views + GitHub webhooks |
| mcp | MCP server (stdio + HTTP/SSE) |

## Core Requirements (Static)
- Parse codebases and extract functions, classes, endpoints, models
- Build Neo4j knowledge graph + ChromaDB vector store
- LLM queries with low/medium/high effort tiers
- REST API + MCP server for AI assistants (Claude Desktop, Cursor)
- GitHub webhook for auto re-indexing on push
- JWT authentication with API token support

## Implemented Features (with dates)

### Initial Codebase (pre-existing)
- Full Django REST API for project CRUD, members, ingestion
- Parser for Python, JS/TS, Go, Rust, Java
- Neo4j graph + ChromaDB vector store
- Celery tasks for async ingestion (local, GitHub, webhook)
- MCP server (stdio + HTTP/SSE)
- GitHub OAuth integration
- GitHub webhook handler (Python-only, no branch filtering)

### Branch-Specific Webhook Enhancement (2026-02)
- **`webhook_branch` field** on Project model — configurable via `PATCH /api/projects/<slug>/` 
- **Branch filtering** in webhook handler — only processes pushes to the watched branch (falls back to `github_default_branch`)
- **Multi-language support** — webhook now covers `.py`, `.js`, `.jsx`, `.ts`, `.tsx`, `.go`, `.rs`, `.java`
- **`WebhookEvent` model** — logs every matched webhook event (branch, commit SHA, commit message, pusher, changed/deleted files, Celery task ID, status)
- **`GET /api/projects/<slug>/webhook-events/`** — lists all webhook events for a project with optional `?branch=` filter

## Migrations Added
- `projects/0003_add_webhook_branch.py` — adds `webhook_branch` field
- `intelligence/0005_add_webhook_event.py` — creates `WebhookEvent` table

## Prioritized Backlog

### P0 (Critical)
- None outstanding

### P1 (High)
- Webhook event status update: mark `WebhookEvent.status` as `processed`/`failed` when Celery task completes
- Admin panel registration for `WebhookEvent` model

### P2 (Nice to have)
- Pagination for `/webhook-events/` endpoint
- Webhook event detail endpoint (GET by ID)
- Filtering webhook events by date range or status
