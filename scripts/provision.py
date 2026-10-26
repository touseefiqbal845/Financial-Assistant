import os

import psycopg
from dotenv import load_dotenv
from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver
from psycopg import sql
from psycopg.conninfo import make_conninfo

from financial_assistant.platform import run_async


async def checkpoints(url: str) -> None:
    async with AsyncPostgresSaver.from_conn_string(make_conninfo(url, connect_timeout=5)) as saver:
        await saver.setup()


def main() -> None:
    load_dotenv(".env")
    url = os.environ["FIN_MIGRATION_DATABASE_URL"].replace("postgresql+psycopg://", "postgresql://")
    run_async(checkpoints(url))
    with psycopg.connect(url, autocommit=True) as connection:
        for role, variable in (
            ("finance_app", "DB_APP_PASSWORD"),
            ("finance_reader", "DB_READER_PASSWORD"),
            ("finance_ingest", "DB_INGEST_PASSWORD"),
        ):
            password = os.environ[variable]
            if len(password) < 24:
                raise ValueError("Database passwords must contain at least 24 characters.")
            if not connection.execute(
                "SELECT 1 FROM pg_roles WHERE rolname = %s", (role,)
            ).fetchone():
                connection.execute(
                    sql.SQL("CREATE ROLE {} LOGIN PASSWORD {} NOSUPERUSER NOBYPASSRLS").format(
                        sql.Identifier(role), sql.Literal(password)
                    )
                )
            else:
                connection.execute(
                    sql.SQL("ALTER ROLE {} PASSWORD {} NOSUPERUSER NOBYPASSRLS").format(
                        sql.Identifier(role), sql.Literal(password)
                    )
                )
            connection.execute(
                sql.SQL("GRANT USAGE ON SCHEMA public TO {}").format(sql.Identifier(role))
            )
        connection.execute("REVOKE CREATE ON SCHEMA public FROM PUBLIC")
        connection.execute("GRANT SELECT ON financial_records, document_chunks TO finance_reader")
        connection.execute(
            "GRANT SELECT, INSERT, UPDATE, DELETE ON financial_records, document_chunks TO finance_ingest"
        )
        connection.execute(
            "GRANT SELECT, INSERT, UPDATE, DELETE ON executions, audit_events, checkpoints, checkpoint_blobs, checkpoint_writes, checkpoint_migrations TO finance_app"
        )
        connection.execute("ALTER ROLE finance_reader SET statement_timeout = '10000'")
        connection.execute("ALTER ROLE finance_reader SET default_transaction_read_only = on")
    print("Provisioned scoped source roles and application/checkpoint privileges.")


if __name__ == "__main__":
    main()
