from decimal import Decimal
from typing import Literal

from pydantic import Field, SecretStr, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="FIN_", env_file=".env", extra="ignore")

    environment: Literal["development", "test", "production"] = "production"
    database_url: SecretStr
    source_database_url: SecretStr
    checkpoint_url: SecretStr
    ingest_database_url: SecretStr | None = None
    migration_database_url: SecretStr | None = None
    openai_api_key: SecretStr | None = None
    main_model: str = "gpt-6-luna"
    planner_model: str = "gpt-6.1-sol"
    data_model: str = "gpt-6-luna"
    document_model: str = "gpt-6-luna"
    analysis_model: str = "gpt-6.1-sol"
    embedding_model: str = "text-embedding-3-small"
    embedding_dimensions: int = Field(default=1536, ge=1, le=1536)
    dev_auth_enabled: bool = False
    dev_token: SecretStr | None = None
    oidc_jwks_url: str | None = None
    oidc_issuer: str | None = None
    oidc_audience: str | None = None
    metrics_token: SecretStr | None = None
    max_tasks: int = Field(default=6, ge=1, le=12)
    max_concurrency: int = Field(default=2, ge=1, le=4)
    max_model_calls: int = Field(default=16, ge=1, le=30)
    max_tokens: int = Field(default=24000, ge=1000, le=100000)
    max_cost_usd: Decimal = Field(default=Decimal("0.25"), gt=0)
    execution_timeout_seconds: int = Field(default=180, ge=5, le=600)
    tool_timeout_seconds: int = Field(default=15, ge=1, le=60)
    max_output_tokens: int = Field(default=1400, ge=256, le=4096)
    pricing_version: str = "2026-10-26-estimate"
    pricing: dict[str, tuple[Decimal, Decimal]] = {
        "gpt-6-luna": (Decimal("0.10"), Decimal("0.50")),
        "gpt-6.1-sol": (Decimal("2.00"), Decimal("10.00")),
        "text-embedding-3-small": (Decimal("0.02"), Decimal("0")),
    }

    @model_validator(mode="after")
    def validate_security(self) -> "Settings":
        if self.embedding_dimensions != 1536:
            raise ValueError(
                "Schema requires 1536 dimensions; migrate and reindex before changing."
            )
        if self.dev_auth_enabled:
            if self.environment not in {"development", "test"}:
                raise ValueError("Development authentication is forbidden in production.")
            if not self.dev_token or len(self.dev_token.get_secret_value()) < 32:
                raise ValueError("Development token must contain at least 32 characters.")
        elif not all((self.oidc_jwks_url, self.oidc_issuer, self.oidc_audience)):
            raise ValueError("OIDC configuration is required when development auth is disabled.")
        if self.environment == "production":
            if not str(self.oidc_jwks_url).startswith("https://"):
                raise ValueError("Production JWKS endpoint must use HTTPS.")
        return self
