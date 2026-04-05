#!/bin/bash
# Quick setup: register, login, create project, ingest, and get MCP token
# Usage: ./scripts/mcp_quickstart.sh <email> <password> <project_name> <code_path>

set -e

API_URL="${CODEVAULT_URL:-http://localhost:8000}"
EMAIL="${1:?Usage: $0 <email> <password> <project_name> <code_path>}"
PASSWORD="${2:?Usage: $0 <email> <password> <project_name> <code_path>}"
PROJECT_NAME="${3:?Usage: $0 <email> <password> <project_name> <code_path>}"
CODE_PATH="${4:?Usage: $0 <email> <password> <project_name> <code_path>}"

echo "🚀 CodeVault MCP Quick Start"
echo "============================="

# Register (ignore error if already exists)
echo "📝 Registering user..."
curl -s -X POST "$API_URL/api/auth/register/" \
  -H "Content-Type: application/json" \
  -d "{\"email\": \"$EMAIL\", \"name\": \"Developer\", \"password\": \"$PASSWORD\", \"password_confirm\": \"$PASSWORD\"}" > /dev/null 2>&1 || true

# Login
echo "🔑 Logging in..."
LOGIN_RESPONSE=$(curl -s -X POST "$API_URL/api/auth/login/" \
  -H "Content-Type: application/json" \
  -d "{\"email\": \"$EMAIL\", \"password\": \"$PASSWORD\"}")
JWT=$(echo "$LOGIN_RESPONSE" | python3 -c "import sys,json; print(json.load(sys.stdin)['access'])")

if [ -z "$JWT" ]; then
    echo "❌ Login failed. Check your credentials."
    exit 1
fi
echo "   ✅ Logged in"

# Create project
echo "📁 Creating project '$PROJECT_NAME'..."
curl -s -X POST "$API_URL/api/projects/" \
  -H "Authorization: Bearer $JWT" \
  -H "Content-Type: application/json" \
  -d "{\"name\": \"$PROJECT_NAME\", \"description\": \"Indexed by CodeVault\", \"local_path\": \"$CODE_PATH\"}" > /dev/null 2>&1 || true

# Get project slug
SLUG=$(echo "$PROJECT_NAME" | python3 -c "import sys; print(sys.stdin.read().strip().lower().replace(' ', '-'))")

# Ingest
echo "🔍 Ingesting codebase (this may take a while)..."
INGEST_RESPONSE=$(curl -s -X POST "$API_URL/api/projects/$SLUG/ingest/" \
  -H "Authorization: Bearer $JWT" \
  -H "Content-Type: application/json" \
  -d "{\"path\": \"$CODE_PATH\", \"sync\": true, \"clear\": true}")
echo "   $INGEST_RESPONSE"

# Create API token for MCP
echo "🎫 Creating MCP API token..."
TOKEN_RESPONSE=$(curl -s -X POST "$API_URL/api/auth/tokens/" \
  -H "Authorization: Bearer $JWT" \
  -H "Content-Type: application/json" \
  -d '{"name": "MCP Server"}')
API_TOKEN=$(echo "$TOKEN_RESPONSE" | python3 -c "import sys,json; print(json.load(sys.stdin)['token'])")

echo ""
echo "✅ Done! Your project '$PROJECT_NAME' is indexed and ready."
echo ""
echo "📋 Add this to your Claude Desktop config:"
echo ""
echo "{
  \"mcpServers\": {
    \"codevault\": {
      \"command\": \"python\",
      \"args\": [\"-m\", \"apps.mcp.server\", \"--api-url\", \"$API_URL\", \"--api-token\", \"$API_TOKEN\"],
      \"cwd\": \"$(pwd)\"
    }
  }
}"
echo ""
echo "Config file locations:"
echo "  macOS:   ~/Library/Application Support/Claude/claude_desktop_config.json"
echo "  Windows: %APPDATA%\\Claude\\claude_desktop_config.json"
echo "  Linux:   ~/.config/claude/claude_desktop_config.json"
