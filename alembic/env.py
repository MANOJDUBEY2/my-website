from logging.config import file_config
from sqlalchemy import engine_from_config
from sqlalchemy import pool
from alembic import context

# ── Import your Base and Models ──────────────────────────────────────────────
# Humne 'app.database' se Base ko aur 'app' se models ko import kiya hai
from app.database import Base, DATABASE_URL
from app import models  # Taaki Alembic ko saare tables mil jayein

# Alembic Config object
config = context.config

# Interpret the config file for Python logging.
if config.config_file_name is not None:
    file_config(config.config_file_name)

# ── Set target metadata ──────────────────────────────────────────────────────
# Yahan hum Alembic ko bata rahe hain ki hamare models ka 'map' kya hai
target_metadata = Base.metadata

def run_migrations_offline() -> None:
    """Run migrations in 'offline' mode."""
    url = DATABASE_URL
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )

    with context.begin_transaction():
        context.run_migrations()

def run_migrations_online() -> None:
    """Run migrations in 'online' mode."""
    # Hum dynamically DATABASE_URL use kar rahe hain jo database.py mein hai
    configuration = config.get_section(config.config_ini_section, {})
    configuration["sqlalchemy.url"] = DATABASE_URL
    
    connectable = engine_from_config(
        configuration,
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )

    with connectable.connect() as connection:
        context.configure(
            connection=connection, 
            target_metadata=target_metadata
        )

        with context.begin_transaction():
            context.run_migrations()

if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()