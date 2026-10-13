from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic import Field, field_validator
from urllib.parse import urlparse
from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, sessionmaker

class Settings(BaseSettings):
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
