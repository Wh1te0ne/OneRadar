from functools import lru_cache
from os import getenv

from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker


def normalize_database_url(database_url: str) -> str:
    if database_url.startswith('postgresql+'):
        return database_url
    if database_url.startswith('postgresql://'):
        return database_url.replace('postgresql://', 'postgresql+psycopg://', 1)
    if database_url.startswith('postgres://'):
        return database_url.replace('postgres://', 'postgresql+psycopg://', 1)
    return database_url


@lru_cache
def get_database_url() -> str:
    database_url = getenv('ONERADAR_DATABASE_URL', 'sqlite+pysqlite:///./oneradar.db')
    return normalize_database_url(database_url)


engine = create_engine(get_database_url(), pool_pre_ping=True)
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)


def get_db() -> Session:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
