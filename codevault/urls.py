from django.contrib import admin
from django.urls import path, include
from django.http import JsonResponse
import time


def health_check(request):
    """Basic liveness probe."""
    return JsonResponse({"status": "ok", "service": "codevault"})


def readiness_check(request):
    """
    Readiness probe — reports the status of all backend dependencies.
    Always returns 200 so that a slow-starting dependency does not crash
    the app on startup.  Callers can inspect the per-service 'checks' dict
    to determine whether individual services are available.
    """
    checks = {}

    # PostgreSQL
    try:
        from django.db import connection
        with connection.cursor() as cursor:
            cursor.execute("SELECT 1")
        checks['database'] = 'ok'
    except Exception as e:
        checks['database'] = f'error: {str(e)[:100]}'

    # Redis
    try:
        from django.core.cache import cache
        cache.set('_health', 'ok', 10)
        val = cache.get('_health')
        checks['redis'] = 'ok' if val == 'ok' else 'error: cache miss'
    except Exception as e:
        checks['redis'] = f'error: {str(e)[:100]}'

    # Neo4j — short timeout so a missing instance doesn't stall startup
    try:
        from django.conf import settings as s
        from neo4j import GraphDatabase
        driver = GraphDatabase.driver(
            s.NEO4J_URI,
            auth=(s.NEO4J_USER, s.NEO4J_PASSWORD),
            connection_timeout=5,
        )
        with driver.session() as session:
            session.run("RETURN 1")
        driver.close()
        checks['neo4j'] = 'ok'
    except Exception as e:
        checks['neo4j'] = f'error: {str(e)[:100]}'

    # ChromaDB — use HTTP client when CHROMA_HOST is configured, otherwise skip
    try:
        import chromadb
        from django.conf import settings as s
        chroma_host = getattr(s, 'CHROMA_HOST', None)
        if chroma_host:
            chroma_port = getattr(s, 'CHROMA_PORT', 8000)
            client = chromadb.HttpClient(host=chroma_host, port=chroma_port)
            client.heartbeat()
            checks['chromadb'] = 'ok'
        else:
            checks['chromadb'] = 'skipped: CHROMA_HOST not configured'
    except Exception as e:
        checks['chromadb'] = f'error: {str(e)[:100]}'

    all_ok = all(v == 'ok' for v in checks.values())
    return JsonResponse(
        {"status": "ok" if all_ok else "degraded", "service": "codevault", "checks": checks},
        status=200,
    )


urlpatterns = [
    path('admin/', admin.site.urls),
    path('health/', health_check),
    path('ready/', readiness_check),
    path('api/auth/', include('apps.accounts.urls')),
    path('api/', include('apps.api.urls')),
    path('mcp/', include('apps.mcp.urls')),
]
