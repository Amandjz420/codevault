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

# Collect static files at build time so they are baked into the image.
# A dummy SECRET_KEY is provided so Django can initialise without real env vars.
# DATABASE_URL is pointed at a dummy value; collectstatic never touches the DB.
RUN SECRET_KEY=build-time-static-collection-only \
    DATABASE_URL=sqlite:////tmp/build.db \
    python manage.py collectstatic --noinput

EXPOSE 8000

# Default command (override in docker-compose.yml)
CMD ["gunicorn", "codevault.asgi:application", "--bind", "0.0.0.0:8000", "--workers", "4", "--worker-class", "uvicorn.workers.UvicornWorker", "--timeout", "120"]
