import os
from django.core.wsgi import get_wsgi_application
from whitenoise import WhiteNoise
from pathlib import Path

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'codevault.settings')

_django_app = get_wsgi_application()

# Wrap the WSGI application with WhiteNoise so static files are served
# directly at the WSGI layer, providing a reliable fallback regardless of
# which server is used.
_static_root = Path(__file__).resolve().parent.parent / 'staticfiles'
application = WhiteNoise(_django_app, root=str(_static_root), prefix='static')
