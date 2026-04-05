from django.contrib import admin
from django.urls import path, include
from django.http import JsonResponse
import time


def health_check(request):
    """Basic liveness probe."""
    return JsonResponse({"status": "ok", "service": "codevault"})


def readiness_check(request):
    """
    Deep readiness probe — checks all backend dependencies.
    Returns 503 if any critical service is unavailable.
    """
    checks = {}
    all_ok = True

    # PostgreSQL
    try:
        from django.db import connection
        with connection.cursor() as cursor:
            cursor.execute("SELECT 1")
        checks['database'] = 'ok'
    except Exception as e:
        checks['database'] = f'error: {str(e)[:100]}'
        all_ok = False

    # Redis
    try:
        from django.core.cache import cache
        cache.set('_health', 'ok', 10)
        val = cache.get('_health')
        checks['redis'] = 'ok' if val == 'ok' else 'error: cache miss'
        if val != 'ok':
            all_ok = False
    except Exception as e:
        checks['redis'] = f'error: {str(e)[:100]}'
        all_ok = False

    # Neo4j
    try:
        from django.conf import settings as s
        from neo4j import GraphDatabase
        driver = GraphDatabase.driver(s.NEO4J_URI, auth=(s.NEO4J_USER, s.NEO4J_PASSWORD))
        with driver.session() as session:
            session.run("RETURN 1")
        driver.close()
        checks['neo4j'] = 'ok'
    except Exception as e:
        checks['neo4j'] = f'error: {str(e)[:100]}'
        all_ok = False

    # ChromaDB
    try:
        import chromadb
        from django.conf import settings as s
        client = chromadb.PersistentClient(path=s.CHROMA_DB_PATH)
        client.heartbeat()
        checks['chromadb'] = 'ok'
    except Exception as e:
        checks['chromadb'] = f'error: {str(e)[:100]}'
        all_ok = False

    status_code = 200 if all_ok else 503
    return JsonResponse(
        {"status": "ok" if all_ok else "degraded", "service": "codevault", "checks": checks},
        status=status_code,
    )


urlpatterns = [
    path('admin/', admin.site.urls),
    path('health/', health_check),
    path('ready/', readiness_check),
    path('api/auth/', include('apps.accounts.urls')),
    path('api/', include('apps.api.urls')),
    path('mcp/', include('apps.mcp.urls')),
]
