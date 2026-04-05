# MCP Server Setup Guide

Connect CodeVault to your AI coding assistant for deep codebase understanding.

## Claude Desktop (Recommended)

### 1. Get an API Token

```bash
# Login and get JWT
curl -X POST http://localhost:8000/api/auth/login/ \
  -H "Content-Type: application/json" \
  -d '{"email": "you@example.com", "password": "your_password"}'

# Create a long-lived API token (recommended over JWT)
curl -X POST http://localhost:8000/api/auth/tokens/ \
  -H "Authorization: Bearer <JWT_FROM_STEP_ABOVE>" \
  -H "Content-Type: application/json" \
  -d '{"name": "Claude Desktop"}'
# Save the "token" value from the response
```

### 2. Configure Claude Desktop

Edit your Claude Desktop config file:
- **macOS:** `~/Library/Application Support/Claude/claude_desktop_config.json`
- **Windows:** `%APPDATA%\Claude\claude_desktop_config.json`
- **Linux:** `~/.config/claude/claude_desktop_config.json`

```json
{
  "mcpServers": {
    "codevault": {
      "command": "python",
      "args": [
        "-m", "apps.mcp.server",
        "--api-url", "http://localhost:8000",
        "--api-token", "YOUR_API_TOKEN_HERE"
      ],
      "cwd": "/path/to/codevault"
    }
  }
}
```

### 3. Restart Claude Desktop

Quit and reopen Claude Desktop. You should see "codevault" in the MCP tools list.

### 4. Test It

Ask Claude:
- "Using codevault, list the projects available"
- "Search the codebase for authentication logic in my-project"
- "What API endpoints does my-project expose?"
- "Ask the codebase: how does the payment flow work?"

## Cursor

### Option A: SSE Transport (Recommended)

In Cursor settings, add:

```json
{
  "mcpServers": {
    "codevault": {
      "url": "http://localhost:8000/mcp/sse/",
      "headers": {
        "Authorization": "Bearer YOUR_API_TOKEN_HERE"
      }
    }
  }
}
```

### Option B: stdio Transport

```json
{
  "mcpServers": {
    "codevault": {
      "command": "python",
      "args": ["-m", "apps.mcp.server", "--api-url", "http://localhost:8000", "--api-token", "YOUR_TOKEN"],
      "cwd": "/path/to/codevault"
    }
  }
}
```

## Windsurf / Continue.dev / Other MCP Clients

Any MCP-compatible client can connect using either transport:

**stdio:** Run `python -m apps.mcp.server --api-url http://localhost:8000 --api-token YOUR_TOKEN`

**HTTP:** POST JSON-RPC requests to `http://localhost:8000/mcp/http/` with `Authorization: Bearer YOUR_TOKEN`

## Available Tools

| Tool | Description |
|------|-------------|
| `list_projects` | List accessible projects (no project slug needed) |
| `get_project_stats` | Project overview: files, functions, classes, endpoints |
| `search_codebase` | Semantic code search by natural language |
| `get_function` | Full function details with endpoint/signal context |
| `get_class` | Class details with fields and relationships |
| `list_api_endpoints` | All REST API routes in the project |
| `list_models` | All data models/entities |
| `list_files` | Indexed files with entity counts |
| `get_file_summary` | Detailed breakdown of a single file |
| `get_dependency_graph` | Trace dependencies and callers |
| `ask_codebase` | LLM-powered Q&A about the codebase |

## Troubleshooting

**"Unauthorized" errors:** Your token may have expired. Create a new API token (they don't expire by default).

**"Project not found":** Make sure you've created and ingested the project first. Use `list_projects` to check.

**No results from search:** The project needs to be ingested first. Run: `python manage.py ingest_local <slug> /path/to/project --sync`

**Slow responses on "high" effort:** High effort queries do multi-hop graph traversal + LLM call. Use "medium" for most questions.
