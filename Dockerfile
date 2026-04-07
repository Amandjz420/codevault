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

# Collect static files at build time
RUN SECRET_KEY=build-time-static-collection-only \
    DATABASE_URL=sqlite:////tmp/build.db \
    python manage.py collectstatic --noinput

EXPOSE 8000

CMD ["sh", "-c", "\
    echo '>>> Step 1: migrate' && \
    python manage.py migrate --noinput && \
    echo '>>> Step 2: migrate done' && \
    echo '>>> Step 3: collectstatic' && \
    python manage.py collectstatic --noinput || echo '>>> collectstatic failed, continuing' && \
    echo '>>> Step 4: starting gunicorn on port '${PORT:-8000} && \
    gunicorn codevault.asgi:application \
        --bind 0.0.0.0:${PORT:-8000} \
        --workers 2 \
        --worker-class uvicorn.workers.UvicornWorker \
        --timeout 120 \
        --log-level info \
"]
