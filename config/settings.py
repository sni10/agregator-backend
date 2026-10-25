"""Django settings. All environment-specific values come from env vars / .env, validated in config/app_settings."""
import os
import tempfile
from pathlib import Path

from .app_settings import load_settings

BASE_DIR = Path(__file__).resolve().parent.parent

ENV = load_settings(BASE_DIR / '.env')

SECRET_KEY = ENV.django.secret_key.get_secret_value()
DEBUG = ENV.django.debug
ALLOWED_HOSTS = ENV.django.allowed_hosts

# The app is only reachable through Caddy, which sets X-Forwarded-Proto itself.
# Without this Django treats proxied HTTPS requests as HTTP and admin CSRF checks fail.
SECURE_PROXY_SSL_HEADER = ('HTTP_X_FORWARDED_PROTO', 'https')
SESSION_COOKIE_SECURE = CSRF_COOKIE_SECURE = not DEBUG

# CI sets TEST_REPORTS_DIR: tests also write a JUnit report there (unittest-xml-reporting, a dev dependency)
if os.environ.get('TEST_REPORTS_DIR'):
    TEST_RUNNER = 'xmlrunner.extra.djangotestrunner.XMLTestRunner'
    TEST_OUTPUT_DIR = os.environ['TEST_REPORTS_DIR']
    TEST_OUTPUT_FILE_NAME = 'junit.xml'

INSTALLED_APPS = [
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',
    'django.contrib.postgres',  # full-text search
    'rest_framework',
    'drf_spectacular',
    'corsheaders',
    'publications',
    'publishing_api',
    'public_api',
]

MIDDLEWARE = [
    'django.middleware.security.SecurityMiddleware',
    'whitenoise.middleware.WhiteNoiseMiddleware',  # admin static from the app container: no shared volume with Caddy
    'django.contrib.sessions.middleware.SessionMiddleware',
    'corsheaders.middleware.CorsMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
]

ROOT_URLCONF = 'config.urls'

TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        'DIRS': [],
        'APP_DIRS': True,
        'OPTIONS': {
            'context_processors': [
                'django.template.context_processors.request',
                'django.contrib.auth.context_processors.auth',
                'django.contrib.messages.context_processors.messages',
            ],
        },
    },
]

WSGI_APPLICATION = 'config.wsgi.application'

DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.postgresql',
        'NAME': ENV.db.name,
        'USER': ENV.db.user,
        'PASSWORD': ENV.db.password.get_secret_value(),
        'HOST': ENV.db.host,
        'PORT': ENV.db.port,
    }
}

AUTH_PASSWORD_VALIDATORS = [
    {'NAME': 'django.contrib.auth.password_validation.UserAttributeSimilarityValidator'},
    {'NAME': 'django.contrib.auth.password_validation.MinimumLengthValidator'},
    {'NAME': 'django.contrib.auth.password_validation.CommonPasswordValidator'},
    {'NAME': 'django.contrib.auth.password_validation.NumericPasswordValidator'},
]

LANGUAGE_CODE = 'en-us'
TIME_ZONE = 'UTC'
USE_I18N = True
USE_TZ = True

STATIC_URL = 'static/'
STATIC_ROOT = BASE_DIR / ENV.static.root

MEDIA_URL = ENV.media.url
MEDIA_ROOT = BASE_DIR / ENV.media.root

DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'

PUBLISHING_API_KEY = ENV.publishing.api_key.get_secret_value()  # /publishing/*; empty -> publishing off

SITE_URL = ENV.site.url  # sitemap.xml, news-sitemap.xml, rss.xml link to the front
SITE_NAME = ENV.site.name

CORS_ALLOWED_ORIGINS = ENV.cors.allowed_origins

# Shared by all gunicorn workers of a container (the default LocMemCache is per process, which would multiply
# throttle limits by the worker count). Only throttle counters are stored; losing them on restart is fine.
CACHES = {
    'default': {
        'BACKEND': 'django.core.cache.backends.filebased.FileBasedCache',
        'LOCATION': Path(tempfile.gettempdir()) / 'agregator-cache',
    }
}

REST_FRAMEWORK = {
    'DEFAULT_SCHEMA_CLASS': 'drf_spectacular.openapi.AutoSchema',
    'DEFAULT_AUTHENTICATION_CLASSES': [],  # no users on the API: the pipeline has X-Api-Key, readers are anonymous
    'UNAUTHENTICATED_USER': None,
    'EXCEPTION_HANDLER': 'config.drf.exception_handler',
    'DEFAULT_THROTTLE_CLASSES': ['rest_framework.throttling.ScopedRateThrottle'],
    'DEFAULT_THROTTLE_RATES': {
        'publishing': '120/min',
        'read': '300/min',  # per IP; the SSR server also calls through Caddy, so keep it well above one reader
    },
    # The app runs behind exactly one proxy (Caddy): it sends one X-Forwarded-For value, the client IP
    'NUM_PROXIES': 1,
}

# OpenAPI spec: /api/schema/ (YAML), /api/docs/ (Swagger UI), /api/redoc/; file: manage.py spectacular
SPECTACULAR_SETTINGS = {
    'TITLE': 'Agregator API',
    'DESCRIPTION': (
        'IT / AI / Crypto news.\n\n'
        'Public read API: published stories only, no auth.\n\n'
        'Publishing API (`/publishing/*`): the local pipeline only, header `X-Api-Key` (PUBLISHING_API_KEY). '
        'Create is idempotent by `external_id`; update needs `If-Match: <revision>`.'
    ),
    'VERSION': '0.1.0',
    'SERVE_INCLUDE_SCHEMA': False,
}
