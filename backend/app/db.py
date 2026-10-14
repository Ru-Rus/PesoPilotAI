from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic import Field, field_validator, model_validator
from typing import Literal
from urllib.parse import urlparse
from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, sessionmaker

class Settings(BaseSettings):
    metrics_token: str = ''
    audit_retention_days: int = Field(default=90, ge=7, le=3650)
    ai_limit: int = Field(default=20, ge=1, le=1000)
    ollama_url: str = ''
    ollama_model: str = ''
    model_timeout_seconds: int = Field(default=10, ge=1, le=30)
    app_env: Literal['development', 'test', 'production'] = 'development'
    database_url: str = 'mssql+pyodbc://localhost/PesoPilot?driver=ODBC+Driver+18+for+SQL+Server&trusted_connection=yes&TrustServerCertificate=yes'
    frontend_url: str = 'https://localhost:3010'
    oidc_issuer: str = 'http://localhost:8080/realms/pesopilot'
    oidc_client_id: str = 'pesopilot'
    oidc_client_secret: str = ''
    session_seconds: int = Field(default=28800, ge=60, le=86400)
    session_idle_seconds: int = Field(default=1800, ge=60, le=86400)
    auth_limit: int = Field(default=10, ge=1, le=1000)
    api_limit: int = Field(default=120, ge=1, le=10000)
    rate_window_seconds: int = Field(default=60, ge=1, le=3600)
    model_config = SettingsConfigDict(env_file='.env', extra='ignore')

    @classmethod
    def settings_customise_sources(cls, settings_cls, init_settings, env_settings, dotenv_settings, file_secret_settings):
        def secret_files():
            import os
            from pathlib import Path
            result = {}
            for field in ('database_url', 'oidc_client_secret', 'metrics_token'):
                variable = field.upper()
                path = os.environ.get(variable + '_FILE')
                if not path:
                    continue
                if os.environ.get(variable):
                    raise ValueError('Configure each secret through either environment or a secret file, not both')
                with Path(path).open(encoding='utf-8') as source:
                    value = source.read(8193).strip()
                if not value or len(value) > 8192 or '\x00' in value:
                    raise ValueError('Invalid secret file content')
                result[field] = value
            return result
        return init_settings, env_settings, secret_files, dotenv_settings, file_secret_settings

    @model_validator(mode='after')
    def production_transport(self):
        if self.app_env == 'production':
            from sqlalchemy.engine import make_url
            url = make_url(self.database_url)
            options = {key.lower(): str(value).lower() for key, value in url.query.items()}
            if not self.oidc_issuer.startswith('https://'):
                raise ValueError('Production OIDC requires HTTPS')
            if not self.oidc_client_secret or self.oidc_client_secret.startswith('CHANGE_ME'):
                raise ValueError('Production OIDC requires configured credentials')
            if url.drivername != 'mssql+pyodbc' or options.get('encrypt') not in ('yes', 'true', 'mandatory', 'strict') or options.get('trustservercertificate') not in ('no', 'false') or 'odbc_connect' in options:
                raise ValueError('Production SQL Server requires explicit encryption and certificate verification')
        return self

    @field_validator('ollama_url')
    @classmethod
    def local_model_url(cls, value):
        if value:
            parsed = urlparse(value)
            if parsed.scheme != 'http' or parsed.hostname not in ('127.0.0.1', 'localhost', '::1') or parsed.username or parsed.password or parsed.path not in ('', '/') or parsed.query or parsed.fragment:
                raise ValueError('Only a configured loopback Ollama server is supported; external AI requires separate approval')
        return value.rstrip('/')

    @field_validator('frontend_url')
    @classmethod
    def frontend_origin(cls, value):
        parsed = urlparse(value)
        if parsed.scheme != 'https' or not parsed.hostname or parsed.username or parsed.path not in ('', '/') or parsed.query or parsed.fragment:
            raise ValueError('FRONTEND_URL must be an HTTPS origin')
        return value.rstrip('/')

    @field_validator('oidc_issuer')
    @classmethod
    def issuer_url(cls, value):
        parsed = urlparse(value)
        if not parsed.hostname or parsed.username or parsed.query or parsed.fragment or (parsed.scheme != 'https' and not (parsed.scheme == 'http' and parsed.hostname in ('localhost', '127.0.0.1'))):
            raise ValueError('OIDC issuer must use HTTPS, except loopback local development')
        return value.rstrip('/')

settings = Settings()
engine = create_engine(settings.database_url, pool_pre_ping=True)
Session = sessionmaker(engine)
class Base(DeclarativeBase):
    pass

def session():
    with Session() as db:
        yield db
