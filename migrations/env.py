from alembic import context
from sqlalchemy import create_engine

from financial_assistant.config import Settings
from financial_assistant.persistence.tables import Base

settings = Settings()
if not settings.migration_database_url:
    raise ValueError("FIN_MIGRATION_DATABASE_URL is required.")

engine = create_engine(settings.migration_database_url.get_secret_value())
with engine.connect() as connection:
    context.configure(connection=connection, target_metadata=Base.metadata)
    with context.begin_transaction():
        context.run_migrations()
