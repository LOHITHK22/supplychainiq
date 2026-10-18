"""Apply `sql/ddl/*.sql` in filename order, once each, and set role passwords.

Usage:  uv run python -m supplychainiq.db.migrate

Idempotent: applied files are recorded in `ops.schema_migration` with a checksum.
Editing an already-applied file is an error; add a new numbered file instead.
"""

import hashlib
from pathlib import Path

from sqlalchemy import Connection, text

from supplychainiq.config import get_settings
from supplychainiq.db import get_engine
from supplychainiq.log import configure_logging, get_logger

DDL_DIR = Path(__file__).resolve().parents[3] / "sql" / "ddl"
log = get_logger(__name__)


class MigrationChecksumError(RuntimeError):
    pass


def _checksum(sql: str) -> str:
    return hashlib.sha256(sql.encode("utf-8")).hexdigest()


def _ensure_tracking_table(conn: Connection) -> None:
    conn.execute(text("CREATE SCHEMA IF NOT EXISTS ops"))
    conn.execute(
        text(
            """
            CREATE TABLE IF NOT EXISTS ops.schema_migration (
                filename   TEXT PRIMARY KEY,
                checksum   TEXT NOT NULL,
                applied_at TIMESTAMPTZ NOT NULL DEFAULT now()
            )
            """
        )
    )


def _set_role_passwords(conn: Connection) -> None:
    settings = get_settings()
    passwords = {
        "sciq_ingest": settings.ingest_db_password,
        "sciq_mcp": settings.mcp_db_password,
        "sciq_app": settings.app_db_password,
    }
    for role, secret in passwords.items():
        value = secret.get_secret_value()
        if not value:
            log.warning("role_password_missing", role=role)
            continue
        # ALTER ROLE cannot take bind parameters, so let the server quote the identifier
        # (%I) and the password literal (%L) safely, then run the resulting statement.
        stmt = conn.execute(
            text(
                "SELECT format('ALTER ROLE %I PASSWORD %L', CAST(:role AS text), CAST(:pw AS text))"
            ),
            {"role": role, "pw": value},
        ).scalar_one()
        conn.exec_driver_sql(stmt)


def migrate(ddl_dir: Path = DDL_DIR) -> list[str]:
    """Apply pending migrations. Returns the filenames applied in this call."""
    applied_now: list[str] = []
    with get_engine("admin").begin() as conn:
        _ensure_tracking_table(conn)
        done = {
            filename: checksum
            for filename, checksum in conn.execute(
                text("SELECT filename, checksum FROM ops.schema_migration")
            )
        }
        for path in sorted(ddl_dir.glob("*.sql")):
            sql = path.read_text(encoding="utf-8")
            checksum = _checksum(sql)
            if path.name in done:
                if done[path.name] != checksum:
                    raise MigrationChecksumError(
                        f"{path.name} changed after being applied; add a new migration instead"
                    )
                continue
            conn.exec_driver_sql(sql)
            conn.execute(
                text("INSERT INTO ops.schema_migration (filename, checksum) VALUES (:f, :c)"),
                {"f": path.name, "c": checksum},
            )
            applied_now.append(path.name)
            log.info("migration_applied", file=path.name)
        _set_role_passwords(conn)
    return applied_now


if __name__ == "__main__":
    configure_logging()
    applied = migrate()
    log.info("migrations_complete", applied=len(applied))
