"""Typed configuration sections. Each section reads env vars with its own prefix and validates them."""
from pathlib import Path
from typing import Annotated, Literal
from urllib.parse import urlsplit

from pydantic import BaseModel, Field, SecretStr, field_validator, model_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict

Port = Annotated[int, Field(ge=1, le=65535)]
CommaList = Annotated[list[str], NoDecode]  # "a, b" in env -> ['a', 'b']


def split_commas(value):
    if isinstance(value, str):
        return [item.strip() for item in value.split(',') if item.strip()]
    return value


class Section(BaseSettings):
    model_config = SettingsConfigDict(extra='ignore', env_file_encoding='utf-8')


class DjangoSettings(Section):
    model_config = SettingsConfigDict(env_prefix='DJANGO_')

    secret_key: SecretStr
    debug: bool = False
    allowed_hosts: CommaList = []

    _split_hosts = field_validator('allowed_hosts', mode='before')(split_commas)

    @model_validator(mode='after')
    def check_production(self):
        if self.debug:
            return self
        key = self.secret_key.get_secret_value()
        if len(key) < 50 or key.startswith('django-insecure-'):
            raise ValueError('DJANGO_SECRET_KEY must be a random value of 50+ chars when DJANGO_DEBUG=false')
        if not self.allowed_hosts:
            raise ValueError('DJANGO_ALLOWED_HOSTS is required when DJANGO_DEBUG=false')
        return self


class DatabaseSettings(Section):
    model_config = SettingsConfigDict(env_prefix='DB_')

    name: str
    user: str
    password: SecretStr
    host: str = 'db'  # the compose service
    port: Port = 5432


class CorsSettings(Section):
    model_config = SettingsConfigDict(env_prefix='CORS_')

    allowed_origins: CommaList = []

    _split_origins = field_validator('allowed_origins', mode='before')(split_commas)

    @field_validator('allowed_origins')
    @classmethod
    def check_origins(cls, origins):
        for origin in origins:
            check_origin(origin)
        return origins


def check_origin(origin: str) -> str:
    parts = urlsplit(origin)
    if parts.scheme not in ('http', 'https') or not parts.netloc or parts.path or parts.query:
        raise ValueError(f'"{origin}" must look like scheme://host[:port] without a path')
    return origin


class StaticSettings(Section):
    model_config = SettingsConfigDict(env_prefix='STATIC_')

    root: Path = Path('staticfiles')  # `collectstatic` target; relative to the project root


class MediaSettings(Section):
    """Story images (WebP variants made on upload). Caddy serves them in production, Django only with DEBUG."""

    model_config = SettingsConfigDict(env_prefix='MEDIA_')

    root: Path = Path('media')  # relative to the project root
    url: str = '/media/'  # absolute in production (https://api.<domain>/media/): the front links to it directly

    @field_validator('url')
    @classmethod
    def check_url(cls, url):
        if not url.endswith('/'):
            raise ValueError('must end with /')
        return url


class SiteSettings(Section):
    """The public site (agregator-front): links in the sitemaps and the RSS feed point there, not to the API."""

    model_config = SettingsConfigDict(env_prefix='SITE_')

    url: str = 'http://localhost:5173'
    name: str = 'Renews'  # Google News: the publication name in news-sitemap.xml

    @field_validator('url')
    @classmethod
    def check_url(cls, url):
        return check_origin(url)


class EmailSettings(Section):
    """Account emails (confirmation, password reset). Production: Brevo SMTP, like the gallery."""

    model_config = SettingsConfigDict(env_prefix='EMAIL_')

    backend: Literal['console', 'smtp'] = 'console'  # console prints emails to stdout (development)
    host: str = 'smtp-relay.brevo.com'
    port: Port = 587
    user: str = ''
    password: SecretStr = SecretStr('')
    use_tls: bool = True
    timeout: int = Field(10, ge=1, description='SMTP connect/send timeout, seconds')
    sender: str = 'Renews <noreply@localhost>'


class ContactSettings(Section):
    """POST /contact emails go here. Never sent to clients; the real address lives only in the server's .env."""

    model_config = SettingsConfigDict(env_prefix='CONTACT_')

    email: str = ''  # empty -> messages are only stored (admin), no email


class TurnstileSettings(Section):
    """Cloudflare Turnstile captcha on POST /contact. The site key is the front's, only the secret is here."""

    model_config = SettingsConfigDict(env_prefix='TURNSTILE_')

    secret: SecretStr = SecretStr('')  # empty -> Cloudflare's always-pass test key (dev, tests); set it in production


class PublishingSettings(Section):
    """Publishing API for the local pipeline (/publishing/*, header X-Api-Key)."""

    model_config = SettingsConfigDict(env_prefix='PUBLISHING_')

    api_key: SecretStr = SecretStr('')  # empty -> the API is off (always 403). Generate: openssl rand -hex 32
    # minutes between stories the pipeline publishes in one batch: they go live one by one, not all at once.
    # 0 -> each at once
    spread_minutes: int = Field(0, ge=0, le=240)

    @field_validator('api_key')
    @classmethod
    def check_key(cls, key):
        if key.get_secret_value() and len(key.get_secret_value()) < 32:
            raise ValueError('must be at least 32 chars (openssl rand -hex 32) or empty to disable publishing')
        return key


class AppSettings(BaseModel):
    django: DjangoSettings
    db: DatabaseSettings
    cors: CorsSettings
    static: StaticSettings
    media: MediaSettings
    site: SiteSettings
    email: EmailSettings
    contact: ContactSettings
    turnstile: TurnstileSettings
    publishing: PublishingSettings
