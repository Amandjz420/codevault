#!/bin/sh
set -e

echo "=== CodeVault startup ==="

# Wait for PostgreSQL to be ready (up to 60s)
echo "Waiting for database..."
python - <<'EOF'
import os, sys, time, django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'codevault.settings')
django.setup()
from django.db import connections
from django.db.utils import OperationalError

for attempt in range(30):
    try:
        connections['default'].ensure_connection()
        print(f"Database ready after {attempt * 2}s")
        sys.exit(0)
    except OperationalError as e:
        print(f"DB not ready ({e}), retrying in 2s...")
        time.sleep(2)

print("ERROR: Database never became ready after 60s")
sys.exit(1)
EOF

echo "Running migrations..."
python manage.py migrate --noinput

echo "Collecting static files..."
python manage.py collectstatic --noinput || echo "WARNING: collectstatic failed, continuing"

echo "Starting gunicorn on port ${PORT:-8000}..."
exec gunicorn codevault.asgi:application \
    --bind "0.0.0.0:${PORT:-8000}" \
    --workers 4 \
    --worker-class uvicorn.workers.UvicornWorker \
    --timeout 120 \
    --log-level info
