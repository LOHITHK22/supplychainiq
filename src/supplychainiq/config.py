"""Typed configuration loaded from environment variables and `.env`.

Secrets are `SecretStr`, so they never appear in logs or reprs by accident.
"""

from functools import lru_cache
from typing import Literal

from pydantic import SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    postgres_host: str = "localhost"
    postgres_port: int = 5433
    postgres_db: str = "supplychainiq"
    postgres_user: str = "sciq_admin"
    postgres_password: SecretStr = SecretStr("")

    ingest_db_password: SecretStr = SecretStr("")
    mcp_db_password: SecretStr = SecretStr("")
    app_db_password: SecretStr = SecretStr("")

    fred_api_key: SecretStr = SecretStr("")
    bls_api_key: SecretStr = SecretStr("")
    census_api_key: SecretStr = SecretStr("")

    log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR"] = "INFO"
    log_format: Literal["json", "console"] = "json"

    def database_url(self, role: Literal["admin", "ingest", "mcp", "app"] = "ingest") -> str:
        """SQLAlchemy URL for one of the database roles."""
        users = {
            "admin": (self.postgres_user, self.postgres_password),
            "ingest": ("sciq_ingest", self.ingest_db_password),
            "mcp": ("sciq_mcp", self.mcp_db_password),
            "app": ("sciq_app", self.app_db_password),
        }
        user, password = users[role]
        return (
            f"postgresql+psycopg://{user}:{password.get_secret_value()}"
            f"@{self.postgres_host}:{self.postgres_port}/{self.postgres_db}"
        )


@lru_cache
def get_settings() -> Settings:
    return Settings()
