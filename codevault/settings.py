import os
from pathlib import Path
from datetime import timedelta
from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent.parent
load_dotenv(BASE_DIR / '.env')

SECRET_KEY = os.environ.get('SECRET_KEY', 'django-insecure-dev-key-change-in-production')
DEBUG = os.environ.get('DEBUG', 'True') == 'True'
ALLOWED_HOSTS = os.environ.get('ALLOWED_HOSTS', 'localhost,127.0.0.1').split(',')

DJANGO_APPS = [
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',
]

THIRD_PARTY_APPS = [
    'rest_framework',
    'rest_framework_simplejwt',
    'corsheaders',
    'django_celery_beat',
    'django_celery_results',
]

LOCAL_APPS = [
    'apps.accounts',
    'apps.projects',
    'apps.intelligence',
    'apps.api',
    'apps.mcp',
]

INSTALLED_APPS = DJANGO_APPS + THIRD_PARTY_APPS + LOCAL_APPS

MIDDLEWARE = [
    'django.middleware.security.SecurityMiddleware',
    # WhiteNoise must be immediately after SecurityMiddleware so it can serve
    # static files (including Django admin CSS/JS) before any other middleware
    # inspects or short-circuits the request.
    'whitenoise.middleware.WhiteNoiseMiddleware',
    'corsheaders.middleware.CorsMiddleware',
    'apps.api.middleware.RequestTimingMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
    'apps.api.middleware.RateLimitMiddleware',
]

ROOT_URLCONF = 'codevault.urls'

TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        'DIRS': [BASE_DIR / 'templates'],
        'APP_DIRS': True,
        'OPTIONS': {
            'context_processors': [
                'django.template.context_processors.debug',
                'django.template.context_processors.request',
                'django.contrib.auth.context_processors.auth',
                'django.contrib.messages.context_processors.messages',
            ],
        },
    },
]

WSGI_APPLICATION = 'codevault.wsgi.application'
ASGI_APPLICATION = 'codevault.asgi.application'

import dj_database_url
DATABASES = {
    'default': dj_database_url.config(
        default=os.environ.get(
            'DATABASE_URL',
            'postgresql://codevault:codevault_pass@localhost:5432/codevault'
        ),
        conn_max_age=600,
    )
}

AUTH_USER_MODEL = 'accounts.User'

AUTH_PASSWORD_VALIDATORS = [
    {'NAME': 'django.contrib.auth.password_validation.UserAttributeSimilarityValidator'},
    {'NAME': 'django.contrib.auth.password_validation.MinimumLengthValidator'},
    {'NAME': 'django.contrib.auth.password_validation.CommonPasswordValidator'},
    {'NAME': 'django.contrib.auth.password_validation.NumericPasswordValidator'},
]

REST_FRAMEWORK = {
    'DEFAULT_AUTHENTICATION_CLASSES': [
        'rest_framework_simplejwt.authentication.JWTAuthentication',
    ],
    'DEFAULT_PERMISSION_CLASSES': [
        'rest_framework.permissions.IsAuthenticated',
    ],
    'DEFAULT_PAGINATION_CLASS': 'rest_framework.pagination.PageNumberPagination',
    'PAGE_SIZE': 50,
    'DEFAULT_THROTTLE_CLASSES': [
        'rest_framework.throttling.AnonRateThrottle',
        'rest_framework.throttling.UserRateThrottle',
    ],
    'DEFAULT_THROTTLE_RATES': {
        'anon': '20/minute',
        'user': '120/minute',
        'query': '30/minute',
    },
}

SIMPLE_JWT = {
    'ACCESS_TOKEN_LIFETIME': timedelta(minutes=60),
    'REFRESH_TOKEN_LIFETIME': timedelta(days=7),
    'ROTATE_REFRESH_TOKENS': True,
    'BLACKLIST_AFTER_ROTATION': False,
    'UPDATE_LAST_LOGIN': True,
    'AUTH_HEADER_TYPES': ('Bearer',),
}

CORS_ALLOW_ALL_ORIGINS = os.environ.get('CORS_ALLOW_ALL_ORIGINS', 'True') == 'True'
CORS_ALLOW_CREDENTIALS = True
CORS_ALLOW_HEADERS = [
    'accept',
    'authorization',
    'content-type',
    'x-csrftoken',
]

# Required for Django 4+ CSRF checks over HTTPS.
# Include every domain that will POST to this app.
_allowed_hosts = os.environ.get('ALLOWED_HOSTS', 'localhost,127.0.0.1').split(',')
CSRF_TRUSTED_ORIGINS = [
    f"https://{host}" for host in _allowed_hosts if host not in ('localhost', '127.0.0.1')
] + ['http://localhost', 'http://127.0.0.1']

# Neo4j
NEO4J_URI = os.environ.get('NEO4J_URI', 'bolt://localhost:7687')
NEO4J_USER = os.environ.get('NEO4J_USER', 'neo4j')
NEO4J_PASSWORD = os.environ.get('NEO4J_PASSWORD', 'codevault_pass')

# ChromaDB — local file mode (dev) or HTTP mode (production/Railway)
CHROMA_DB_PATH = os.environ.get('CHROMA_DB_PATH', str(BASE_DIR / 'chroma_db_data'))
CHROMA_HOST = os.environ.get('CHROMA_HOST', '')       # set in Railway → switches to HttpClient
CHROMA_PORT = int(os.environ.get('CHROMA_PORT', '8000'))

# LLM API Keys
OPENAI_API_KEY = os.environ.get('OPENAI_API_KEY', '')
ANTHROPIC_API_KEY = os.environ.get('ANTHROPIC_API_KEY', '')
GOOGLE_API_KEY = os.environ.get('GOOGLE_API_KEY', '')

# Celery
CELERY_BROKER_URL = os.environ.get('REDIS_URL', 'redis://localhost:6379/0')
CELERY_RESULT_BACKEND = 'django-db'
CELERY_CACHE_BACKEND = 'default'
CELERY_BEAT_SCHEDULER = 'django_celery_beat.schedulers:DatabaseScheduler'
CELERY_ACCEPT_CONTENT = ['json']
CELERY_TASK_SERIALIZER = 'json'
CELERY_RESULT_SERIALIZER = 'json'
CELERY_TIMEZONE = 'UTC'

# Cache (Redis)
CACHES = {
    'default': {
        'BACKEND': 'django.core.cache.backends.redis.RedisCache',
        'LOCATION': os.environ.get('REDIS_URL', 'redis://localhost:6379/0'),
        'TIMEOUT': 300,
        'KEY_PREFIX': 'codevault',
    }
}

# GitHub OAuth
GITHUB_CLIENT_ID = os.environ.get('GITHUB_CLIENT_ID', '')
GITHUB_CLIENT_SECRET = os.environ.get('GITHUB_CLIENT_SECRET', '')
GITHUB_REDIRECT_URI = os.environ.get('GITHUB_REDIRECT_URI', 'https://codevault-production-e2a0.up.railway.app/api/auth/github/callback/')
GITHUB_FRONTEND_CALLBACK_URL = os.environ.get('GITHUB_FRONTEND_CALLBACK_URL', 'https://codestorage.lovable.app/auth/github/success')

# Rate Limiting
RATE_LIMIT_REQUESTS = int(os.environ.get('RATE_LIMIT_REQUESTS', '100'))
RATE_LIMIT_WINDOW = int(os.environ.get('RATE_LIMIT_WINDOW', '60'))  # seconds

# File size limits for ingestion
MAX_FILE_SIZE_BYTES = int(os.environ.get('MAX_FILE_SIZE_BYTES', str(10 * 1024 * 1024)))  # 10MB
MAX_FILES_PER_PROJECT = int(os.environ.get('MAX_FILES_PER_PROJECT', '10000'))

# Static & Media
STATIC_URL = '/static/'
STATIC_ROOT = '/app/staticfiles'

# Use CompressedStaticFilesStorage instead of CompressedManifestStaticFilesStorage.
# The Manifest variant requires a valid staticfiles.json to exist at startup; if
# collectstatic hasn't run (or failed silently during the Docker build) every
# static-file request raises a ValueError and the admin is completely unstyled.
# CompressedStaticFilesStorage compresses files but does NOT require a manifest,
# so the admin CSS/JS are always served even when the manifest is absent.
STATICFILES_STORAGE = 'whitenoise.storage.CompressedStaticFilesStorage'

# Tell WhiteNoise to also search Django's app static-file finders at runtime.
# This ensures admin assets collected into STATIC_ROOT are always discoverable.
WHITENOISE_USE_FINDERS = True

# In DEBUG mode, skip compression and serve files straight from the source
# directories so changes are visible immediately without re-running collectstatic.
WHITENOISE_AUTOREFRESH = DEBUG

MEDIA_URL = '/media/'
MEDIA_ROOT = '/app/staticfiles/media'

LANGUAGE_CODE = 'en-us'
TIME_ZONE = 'UTC'
USE_I18N = True
USE_TZ = True

DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'

LOGGING = {
    'version': 1,
    'disable_existing_loggers': False,
    'formatters': {
        'verbose': {
            'format': '{levelname} {asctime} {module} {message}',
            'style': '{',
        },
    },
    'handlers': {
        'console': {
            'class': 'logging.StreamHandler',
            'formatter': 'verbose',
        },
    },
    'root': {
        'handlers': ['console'],
        'level': 'INFO',
    },
    'loggers': {
        'django': {
            'handlers': ['console'],
            'level': 'INFO',
            'propagate': False,
        },
        'apps': {
            'handlers': ['console'],
            'level': 'DEBUG',
            'propagate': False,
        },
    },
}
