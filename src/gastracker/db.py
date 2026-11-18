"""SQLAlchemy foundation; domain models and migrations follow in Step 2."""

from sqlalchemy import URL, Engine, create_engine
from sqlalchemy.orm import DeclarativeBase

from gastracker.config import Settings


class Base(DeclarativeBase):
    pass


def create_database_engine(settings: Settings) -> Engine:
    settings.database_path.parent.mkdir(parents=True, exist_ok=True)
    return create_engine(
        URL.create("sqlite+pysqlite", database=str(settings.database_path)),
        connect_args={"check_same_thread": False},
    )
