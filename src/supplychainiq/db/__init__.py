"""Database engine helpers."""

from functools import lru_cache
from typing import Literal

from sqlalchemy import Engine, create_engine

from supplychainiq.config import get_settings

Role = Literal["admin", "ingest", "mcp", "app"]


@lru_cache
def get_engine(role: Role = "ingest") -> Engine:
    # hide_parameters keeps bound values (passwords, keys) out of exception messages and logs.
    return create_engine(
        get_settings().database_url(role), pool_pre_ping=True, hide_parameters=True
    )
