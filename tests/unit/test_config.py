from pydantic import SecretStr

from supplychainiq.config import Settings


def test_database_url_uses_role_specific_credentials() -> None:
    s = Settings(
        _env_file=None,
        postgres_host="localhost",
        postgres_port=5433,
        postgres_db="supplychainiq",
        mcp_db_password=SecretStr("m-pw"),
    )
    url = s.database_url("mcp")
    assert url.startswith("postgresql+psycopg://sciq_mcp:m-pw@")
    assert url.endswith(":5433/supplychainiq")


def test_secrets_are_masked_in_repr() -> None:
    s = Settings(_env_file=None, fred_api_key=SecretStr("super-secret"))
    assert "super-secret" not in repr(s)
