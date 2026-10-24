"""Typed configuration sections. Each section reads env vars with its own prefix and validates them."""
from pathlib import Path
from typing import Annotated
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


class PublishingSettings(Section):
    """Publishing API for the local pipeline (/publishing/*, header X-Api-Key)."""

    model_config = SettingsConfigDict(env_prefix='PUBLISHING_')

    api_key: SecretStr = SecretStr('')  # empty -> the API is off (always 403). Generate: openssl rand -hex 32

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
    publishing: PublishingSettings
