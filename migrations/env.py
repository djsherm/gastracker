"""Use the same settings and metadata as the application."""

from alembic import context
from sqlalchemy import URL

from gastracker.config import load_settings
from gastracker.db import Base, create_database_engine

settings = load_settings()
target_metadata = Base.metadata


def run_migrations_offline() -> None:
    context.configure(
        url=URL.create("sqlite+pysqlite", database=str(settings.database_path)),
        target_metadata=target_metadata,
        literal_binds=True,
        render_as_batch=True,
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    engine = create_database_engine(settings)
    try:
        with engine.connect() as connection:
            context.configure(
                connection=connection,
                target_metadata=target_metadata,
                render_as_batch=True,
            )
            with context.begin_transaction():
                context.run_migrations()
    finally:
        engine.dispose()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
