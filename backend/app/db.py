from pydantic_settings import BaseSettings, SettingsConfigDict
from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, sessionmaker

class Settings(BaseSettings):
    database_url: str = 'mssql+pyodbc://localhost/PesoPilot?driver=ODBC+Driver+18+for+SQL+Server&trusted_connection=yes&TrustServerCertificate=yes'
    demo_mode: bool = False
    model_config = SettingsConfigDict(env_file='.env', extra='ignore')

settings = Settings()
engine = create_engine(settings.database_url, pool_pre_ping=True)
Session = sessionmaker(engine)
class Base(DeclarativeBase):
    pass

def session():
    with Session() as db:
        yield db
