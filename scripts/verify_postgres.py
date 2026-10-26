import os
import subprocess
import sys

import psycopg
from dotenv import load_dotenv


def main() -> None:
    load_dotenv()
    owner_url = os.environ["FIN_MIGRATION_DATABASE_URL"]
    url = owner_url.replace("postgresql+psycopg://", "postgresql://")
    with psycopg.connect(url, autocommit=True) as connection:
        exists = connection.execute(
            "SELECT 1 FROM pg_database WHERE datname = 'finance_verify'"
        ).fetchone()
        if not exists:
            connection.execute("CREATE DATABASE finance_verify")
    test_url = owner_url.rsplit("/", 1)[0] + "/finance_verify"
    environment = {
        **os.environ,
        "FIN_MIGRATION_DATABASE_URL": test_url,
        "FIN_TEST_POSTGRES_URL": test_url,
    }
    subprocess.run(
        [sys.executable, "-m", "alembic", "upgrade", "head"], env=environment, check=True
    )
    subprocess.run([sys.executable, "scripts/provision.py"], env=environment, check=True)
    subprocess.run(
        [sys.executable, "-m", "pytest", "tests/integration", "-q"], env=environment, check=True
    )


if __name__ == "__main__":
    main()
