"""Shared fixtures. Integration tests use a separate `<POSTGRES_DB>_test` database."""

from collections.abc import Iterator

import pytest
from sqlalchemy import Engine, create_engine, text

from supplychainiq.config import get_settings
from supplychainiq.db import get_engine


def _admin_url(db: str) -> str:
    s = get_settings()
    return (
        f"postgresql+psycopg://{s.postgres_user}:{s.postgres_password.get_secret_value()}"
        f"@{s.postgres_host}:{s.postgres_port}/{db}"
    )


@pytest.fixture(scope="session")
def test_db() -> Iterator[str]:
    """Create (once) and migrate the test database; skip if PostgreSQL is not running."""
    settings = get_settings()
    test_name = f"{settings.postgres_db}_test"
    try:
        server = create_engine(_admin_url("postgres"), isolation_level="AUTOCOMMIT")
        with server.connect() as conn:
            exists = conn.execute(
                text("SELECT 1 FROM pg_database WHERE datname = :n"), {"n": test_name}
            ).scalar()
            if not exists:
                conn.exec_driver_sql(f'CREATE DATABASE "{test_name}"')
        server.dispose()
    except Exception as exc:
        pytest.skip(
            f"PostgreSQL not available ({type(exc).__name__}); run: docker compose up -d db"
        )

    mp = pytest.MonkeyPatch()
    mp.setenv("POSTGRES_DB", test_name)
    get_settings.cache_clear()
    get_engine.cache_clear()

    from supplychainiq.db.migrate import migrate

    migrate()
    yield test_name
    mp.undo()
    get_settings.cache_clear()
    get_engine.cache_clear()


@pytest.fixture
def engine(test_db: str) -> Iterator[Engine]:
    """Ingest-role engine on a clean test database (data tables truncated per test)."""
    with get_engine("admin").begin() as conn:
        conn.execute(
            text(
                "TRUNCATE raw.market_observation, raw.market_series, ops.ingestion_run, "
                "ops.source_watermark, ops.lineage_edge, ops.dq_result, ops.audit_log"
            )
        )
    yield get_engine("ingest")
