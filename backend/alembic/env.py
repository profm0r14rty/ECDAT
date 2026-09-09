import os
import sys

from alembic import context

# Ensure the project root (backend/) is importable regardless of CWD.
_backend_dir = os.path.join(os.path.dirname(__file__), "..")
if _backend_dir not in sys.path:
    sys.path.insert(0, _backend_dir)

from backend.app.models_orm import Base
from backend.app.db import engine

# Survey all model classes so Alembic can emit migrations for every table.
target_metadata = Base.metadata

def run_migrations_offline() -> None:
    """Run migrations in 'offline' mode.

    This configures the context with just a URL
    and makes emit SQL without needing a Connection.
    """
    url = context.get_configuration().get("sqlalchemy.url")
    context.run_migrations_offline(url=url)

def run_migrations_online() -> None:
    """Run migrations in 'online' mode.

    In this mode we need to create an Engine,
    associate a Connection with the context
    and run the mungs against the DB.
    """
    connectable = engine
    with connectable.connect() as connection:
        context.configure(
            connection=connection, target_metadata=target_metadata
        )
        with context.begin_transaction():
            context.run_migrations()


# Phase 14: this dispatch block was previously missing, so env.py defined the
# two runners above but never executed them — `alembic upgrade head` loaded the
# file and exited 0 without creating a single table.
if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()