"""FRED client parsing, retries and error handling, with HTTP mocked by respx.

Response bodies follow the documented FRED JSON format
(https://fred.stlouisfed.org/docs/api/fred/series_observations.html).
"""

from datetime import UTC, date, datetime
from decimal import Decimal

import httpx
import pytest
import respx

from supplychainiq.ingestion.fred import (
    BASE_URL,
    FredClient,
    FredError,
    parse_last_updated,
    parse_value,
)

SERIES_BODY = {
    "seriess": [
        {
            "id": "RSNSR",
            "title": "Advance Retail Sales: Nonstore Retailers",
            "units": "Millions of Dollars",
            "frequency": "Monthly",
            "seasonal_adjustment": "Seasonally Adjusted",
            "observation_end": "2026-09-01",
            "last_updated": "2026-10-15 07:31:02-05",
            "notes": "Example notes",
        }
    ]
}


def obs_body(rows: list[tuple[str, str, str]], count: int | None = None) -> dict[str, object]:
    return {
        "count": count if count is not None else len(rows),
        "observations": [
            {"realtime_start": rt, "realtime_end": "9999-12-31", "date": d, "value": v}
            for d, v, rt in rows
        ],
    }


@pytest.fixture
def client() -> FredClient:
    return FredClient("k" * 32, min_interval_s=0)


def test_parse_last_updated_pads_hour_only_offset() -> None:
    parsed = parse_last_updated("2026-08-18 09:17:03-05")
    assert parsed.astimezone(UTC) == datetime(2026, 8, 18, 14, 17, 3, tzinfo=UTC)


def test_parse_last_updated_rejects_garbage() -> None:
    with pytest.raises(ValueError):
        parse_last_updated("yesterday")


def test_parse_value_missing_marker() -> None:
    assert parse_value(".") is None
    assert parse_value("123.4") == Decimal("123.4")


def test_missing_api_key_fails_fast() -> None:
    with pytest.raises(FredError, match="FRED_API_KEY"):
        FredClient("")


@respx.mock
def test_get_series_parses_metadata(client: FredClient) -> None:
    respx.get(f"{BASE_URL}/series").mock(return_value=httpx.Response(200, json=SERIES_BODY))
    meta = client.get_series("RSNSR")
    assert meta.series_id == "RSNSR"
    assert meta.observation_end == date(2026, 9, 1)
    assert meta.last_updated.utcoffset() is not None


@respx.mock
def test_observations_keep_every_vintage_and_missing_values(client: FredClient) -> None:
    respx.get(f"{BASE_URL}/series/observations").mock(
        return_value=httpx.Response(
            200,
            json=obs_body(
                [
                    ("2026-08-01", "100.0", "2026-09-16"),  # first estimate
                    ("2026-08-01", "101.5", "2026-10-15"),  # revision
                    ("2026-09-01", ".", "2026-10-15"),  # missing
                ]
            ),
        )
    )
    rows = client.get_observation_vintages("RSNSR", date(2015, 1, 1))
    assert [r.value for r in rows] == [Decimal("100.0"), Decimal("101.5"), None]
    assert rows[1].realtime_start == date(2026, 10, 15)


@respx.mock
def test_observations_paginate_until_count(client: FredClient) -> None:
    route = respx.get(f"{BASE_URL}/series/observations")
    route.side_effect = [
        httpx.Response(200, json=obs_body([("2026-01-01", "1", "2026-02-01")], count=2)),
        httpx.Response(200, json=obs_body([("2026-02-01", "2", "2026-03-01")], count=2)),
    ]
    rows = client.get_observation_vintages("RSNSR", date(2015, 1, 1))
    assert len(rows) == 2
    assert route.calls[1].request.url.params["offset"] == "1"


@respx.mock
def test_retries_on_429_then_succeeds(client: FredClient, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("time.sleep", lambda _s: None)  # skip tenacity backoff waits
    route = respx.get(f"{BASE_URL}/series")
    route.side_effect = [httpx.Response(429), httpx.Response(200, json=SERIES_BODY)]
    assert client.get_series("RSNSR").series_id == "RSNSR"
    assert route.call_count == 2


@respx.mock
def test_gives_up_after_repeated_server_errors(
    client: FredClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr("time.sleep", lambda _s: None)
    route = respx.get(f"{BASE_URL}/series").mock(return_value=httpx.Response(500))
    with pytest.raises(httpx.HTTPStatusError):
        client.get_series("RSNSR")
    assert route.call_count == 5


@respx.mock
def test_bad_request_is_not_retried(client: FredClient) -> None:
    route = respx.get(f"{BASE_URL}/series").mock(
        return_value=httpx.Response(
            400,
            json={"error_code": 400, "error_message": "Bad Request. The series does not exist."},
        )
    )
    with pytest.raises(FredError, match="does not exist"):
        client.get_series("NOPE")
    assert route.call_count == 1


@respx.mock
def test_api_key_is_sent_but_never_in_errors(client: FredClient) -> None:
    route = respx.get(f"{BASE_URL}/series").mock(return_value=httpx.Response(200, json=SERIES_BODY))
    client.get_series("RSNSR")
    assert route.calls[0].request.url.params["api_key"] == "k" * 32
    assert route.calls[0].request.url.params["file_type"] == "json"
