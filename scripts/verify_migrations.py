import os
import subprocess
import sys

import psycopg
from dotenv import load_dotenv
from sqlalchemy import create_engine, inspect

from financial_assistant.persistence.tables import Base


def main() -> None:
    load_dotenv(".env")
    owner_url = os.environ["FIN_MIGRATION_DATABASE_URL"]
    with psycopg.connect(
        owner_url.replace("postgresql+psycopg://", "postgresql://"), autocommit=True
    ) as connection:
        if not connection.execute(
            "SELECT 1 FROM pg_database WHERE datname = 'finance_migration_verify'"
        ).fetchone():
            connection.execute("CREATE DATABASE finance_migration_verify")
    url = owner_url.rsplit("/", 1)[0] + "/finance_migration_verify"
    environment = {**os.environ, "FIN_MIGRATION_DATABASE_URL": url}
    subprocess.run(
        [sys.executable, "-m", "alembic", "upgrade", "head"], env=environment, check=True
    )
    engine = create_engine(url)
    try:
        inspector = inspect(engine)
        for name, table in Base.metadata.tables.items():
            actual = {column["name"] for column in inspector.get_columns(name)}
            assert actual == set(table.columns.keys()), name
        print("Fresh immutable migration matches all application table columns.")
    finally:
        engine.dispose()


if __name__ == "__main__":
    main()
