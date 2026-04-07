FROM python:3.11-slim

WORKDIR /app

# System dependencies
RUN apt-get update && apt-get install -y \
    build-essential \
    libpq-dev \
    git \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt

# Copy project
COPY . .

# Create directories for static files and ChromaDB data
RUN mkdir -p /app/staticfiles /app/chroma_db_data /app/media

# Collect static files (will fail gracefully if DB not available)
RUN python manage.py collectstatic --noinput --no-input 2>/dev/null || true

EXPOSE 8000

# Default command (override in docker-compose.yml)
CMD ["gunicorn", "codevault.asgi:application", "--bind", "0.0.0.0:8000", "--workers", "4", "--worker-class", "uvicorn.workers.UvicornWorker", "--timeout", "120"]
