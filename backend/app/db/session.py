"""
SQLAlchemy engine and session management.

Uses a connection pool (QueuePool, the SQLAlchemy default for non-SQLite
engines) so we never open a new TCP connection per request - this is what
lets the API handle concurrent users without exhausting Postgres connections.
"""
from collections.abc import Generator

from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from app.core.config import get_settings

settings = get_settings()

engine = create_engine(
    settings.DATABASE_URL,
    pool_size=20,          # base pool of persistent connections
    max_overflow=20,       # extra connections allowed under burst load
    pool_pre_ping=True,    # check connection liveness before using it
    pool_recycle=1800,     # recycle connections every 30 min
)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


class Base(DeclarativeBase):
    pass


def get_db() -> Generator[Session, None, None]:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
