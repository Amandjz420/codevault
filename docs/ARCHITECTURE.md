# CodeVault Architecture

## System Overview

CodeVault transforms raw source code into queryable intelligence through a three-stage pipeline:

### Stage 1: Parsing
Source files are parsed using language-specific parsers (Tree-sitter for Python, regex-based for others). The parser extracts structured entities: functions, classes, API endpoints, signals, and cron jobs.

**Supported languages:** Python, JavaScript/TypeScript, Go, Rust, Java

### Stage 2: Indexing
Extracted entities are stored in two complementary systems:
- **Neo4j Knowledge Graph** — Stores structural relationships (File→Function, Endpoint→Handler, Signal→Handler)
- **ChromaDB Vector Store** — Stores code embeddings for semantic search

### Stage 3: Querying
Three query modes:
1. **Semantic Search** — Find code by natural language description (ChromaDB)
2. **Graph Queries** — Navigate code structure and relationships (Neo4j)
3. **LLM-Powered Q&A** — Combines both with an LLM for synthesized answers

## Data Flow

```
Source Code (.py, .js, .ts, .go, .rs, .java)
    │
    ▼
Parser Registry (parsers/__init__.py)
    │ selects parser by file extension
    ▼
Language Parser (e.g., PythonParser)
    │ extracts ParsedFile with entities
    ▼
Ingestion Orchestrator (ingestion.py)
    ├──▶ GraphService.ingest_file()  → Neo4j nodes + relationships
    ├──▶ VectorService.ingest_file() → ChromaDB embeddings
    └──▶ IndexedFile ORM record      → PostgreSQL metadata
```

## MCP Integration

The Model Context Protocol (MCP) server exposes CodeVault's intelligence to AI agents:

```
AI Agent (Claude, Cursor, etc.)
    │ MCP protocol (JSON-RPC)
    ▼
MCP Server
    ├── stdio transport (apps/mcp/server.py)    — Claude Desktop
    ├── HTTP transport  (apps/mcp/views.py)     — Single request
    └── SSE transport   (apps/mcp/views.py)     — Streaming (Cursor)
         │
         ▼
    Tool Handlers
         │ search_codebase, ask_codebase, get_function, etc.
         ▼
    Intelligence Services
         ├── VectorService  → semantic search
         ├── GraphService   → structural queries
         └── LLMService     → synthesized answers
```

## Security Model

- JWT authentication with 60-minute access tokens
- API tokens (HMAC-SHA256 hashed) for long-lived MCP connections
- Project-level RBAC: owner > admin > member > viewer
- Rate limiting: IP-based + user-based throttling
- GitHub webhook HMAC signature verification

## Scaling Considerations

- Neo4j indexes on (namespace, name) for all node types
- ChromaDB HNSW indexing with cosine similarity
- Celery workers for async ingestion (configurable concurrency)
- Redis caching for API responses
- Incremental ingestion via SHA-256 file hashing
- File size limits (10MB) and project file count limits (10k)
