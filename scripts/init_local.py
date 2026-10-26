import secrets
from pathlib import Path


def main() -> None:
    path = Path(".env")
    if path.exists():
        raise SystemExit(".env already exists; refusing to overwrite local secrets.")
    values = {
        name: secrets.token_hex(24)
        for name in (
            "DB_OWNER_PASSWORD",
            "DB_APP_PASSWORD",
            "DB_READER_PASSWORD",
            "DB_INGEST_PASSWORD",
            "FIN_DEV_TOKEN",
            "FIN_METRICS_TOKEN",
        )
    }
    lines = ["FIN_ENVIRONMENT=development", "FIN_DEV_AUTH_ENABLED=true", "FIN_OPENAI_API_KEY="]
    lines += [f"{key}={value}" for key, value in values.items()]
    for name, role, variable in (
        ("FIN_DATABASE_URL", "finance_app", "DB_APP_PASSWORD"),
        ("FIN_SOURCE_DATABASE_URL", "finance_reader", "DB_READER_PASSWORD"),
        ("FIN_MIGRATION_DATABASE_URL", "finance_owner", "DB_OWNER_PASSWORD"),
        ("FIN_INGEST_DATABASE_URL", "finance_ingest", "DB_INGEST_PASSWORD"),
    ):
        lines.append(
            f"{name}=postgresql+psycopg://{role}:{values[variable]}@127.0.0.1:55432/finance"
        )
    lines.append(
        f"FIN_CHECKPOINT_URL=postgresql://finance_app:{values['DB_APP_PASSWORD']}@127.0.0.1:55432/finance"
    )
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(
        "Created ignored .env with distinct development credentials. Configure FIN_OPENAI_API_KEY locally."
    )


if __name__ == "__main__":
    main()
