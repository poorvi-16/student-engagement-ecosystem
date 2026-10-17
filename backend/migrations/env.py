from logging.config import fileConfig

from alembic import context
from sqlmodel import SQLModel

import app.db.models  # noqa: F401  (registers tables on SQLModel.metadata)
from app.config import get_settings
from app.db.session import make_engine, normalize_db_url

config = context.config
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = SQLModel.metadata
DB_URL = normalize_db_url(get_settings().database_url)


def run_migrations_offline() -> None:
    context.configure(url=DB_URL, target_metadata=target_metadata, literal_binds=True, render_as_batch=True)
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    with make_engine(DB_URL).connect() as connection:
        context.configure(connection=connection, target_metadata=target_metadata, render_as_batch=True)
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
