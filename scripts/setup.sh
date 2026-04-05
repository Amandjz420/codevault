#!/bin/bash
# CodeVault Quick Setup Script
# Usage: ./scripts/setup.sh

set -e

echo "🔧 CodeVault Setup"
echo "=================="

# Check prerequisites
command -v python3 >/dev/null 2>&1 || { echo "❌ Python 3 is required but not installed."; exit 1; }
command -v docker >/dev/null 2>&1 || { echo "❌ Docker is required but not installed."; exit 1; }

# Create .env if not exists
if [ ! -f .env ]; then
    echo "📝 Creating .env from template..."
    cp .env.example .env
    # Generate a random secret key
    SECRET_KEY=$(python3 -c "import secrets; print(secrets.token_urlsafe(50))")
    if [[ "$OSTYPE" == "darwin"* ]]; then
        sed -i '' "s/your-secret-key-here/$SECRET_KEY/" .env
    else
        sed -i "s/your-secret-key-here/$SECRET_KEY/" .env
    fi
    echo "   ✅ .env created with generated SECRET_KEY"
    echo "   ⚠️  Edit .env to add your LLM API key (OPENAI_API_KEY, ANTHROPIC_API_KEY, or GOOGLE_API_KEY)"
else
    echo "   ✅ .env already exists"
fi

# Start Docker services
echo ""
echo "🐳 Starting Docker services..."
docker compose up -d

# Wait for services
echo "⏳ Waiting for services to be healthy..."
sleep 10

# Run migrations
echo "📦 Running database migrations..."
docker compose exec -T web python manage.py migrate --noinput

echo ""
echo "✅ CodeVault is running!"
echo ""
echo "   Web:     http://localhost:8000"
echo "   Admin:   http://localhost:8000/admin/"
echo "   Neo4j:   http://localhost:7474"
echo "   Health:  http://localhost:8000/health/"
echo "   Ready:   http://localhost:8000/ready/"
echo ""
echo "Next steps:"
echo "  1. Create a superuser:  docker compose exec web python manage.py createsuperuser"
echo "  2. Get an API token:    See docs/MCP_SETUP.md"
echo "  3. Ingest a project:    docker compose exec web python manage.py ingest_local <slug> <path> --sync"
echo "  4. Connect your AI:     See docs/MCP_SETUP.md"
