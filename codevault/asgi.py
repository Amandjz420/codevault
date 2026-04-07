import os
from django.core.asgi import get_asgi_application
from whitenoise import WhiteNoise
from pathlib import Path

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'codevault.settings')

_django_app = get_asgi_application()

# Wrap the ASGI application with WhiteNoise so static files (including Django
# admin CSS/JS) are served directly by WhiteNoise at the ASGI layer.  This is
# required when running under uvicorn workers because the ASGI protocol path
# bypasses the traditional WSGI-level WhiteNoise wrapping.
_static_root = Path(__file__).resolve().parent.parent / 'staticfiles'
application = WhiteNoise(_django_app, root=str(_static_root), prefix='static')
