"""FRED API client.

Docs: https://fred.stlouisfed.org/docs/api/fred/
Terms: https://fred.stlouisfed.org/docs/api/terms_of_use.html  (no published rate limit;
"reasonable bandwidth" is required, so requests are throttled client-side).
"""

import time
from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal
from types import TracebackType
from typing import Any, Self

import httpx
from tenacity import (
    retry,
    retry_if_exception,
    stop_after_attempt,
    wait_random_exponential,
)

from supplychainiq.log import get_logger

BASE_URL = "https://api.stlouisfed.org/fred"
# Asking for every real-time period returns the full revision history (vintages).
ALL_REALTIME = {"realtime_start": "1776-07-04", "realtime_end": "9999-12-31"}
PAGE_LIMIT = 100_000  # FRED's maximum page size for series/observations

log = get_logger(__name__)


class FredError(RuntimeError):
    """FRED returned an error that retrying will not fix (bad key, unknown series...)."""


@dataclass(frozen=True)
class SeriesMeta:
    series_id: str
    title: str
    units: str | None
    frequency: str | None
    seasonal_adjustment: str | None
    notes: str | None
    last_updated: datetime
    observation_end: date | None


@dataclass(frozen=True)
class Observation:
    obs_date: date
    value: Decimal | None  # None when FRED reports '.' (missing)
    realtime_start: date


def parse_last_updated(raw: str) -> datetime:
    """Parse FRED's `last_updated`, e.g. '2026-08-18 09:17:03-05'.

    The UTC offset has hours only, which `%z` rejects, so pad it to '-0500'.
    """
    stamp, sign, offset = raw[:19], raw[19:20], raw[20:]
    if sign not in {"+", "-"} or not offset.isdigit():
        raise ValueError(f"unexpected last_updated format: {raw!r}")
    offset = offset.ljust(4, "0")
    return datetime.strptime(f"{stamp}{sign}{offset}", "%Y-%m-%d %H:%M:%S%z")


def parse_value(raw: str) -> Decimal | None:
    return None if raw.strip() == "." else Decimal(raw)


def _is_retryable(exc: BaseException) -> bool:
    if isinstance(exc, httpx.TransportError):
        return True
    if isinstance(exc, httpx.HTTPStatusError):
        return exc.response.status_code == 429 or exc.response.status_code >= 500
    return False


class FredClient:
    def __init__(
        self,
        api_key: str,
        *,
        base_url: str = BASE_URL,
        min_interval_s: float = 0.5,
        timeout_s: float = 30.0,
        transport: httpx.BaseTransport | None = None,
    ) -> None:
        if not api_key:
            raise FredError("FRED_API_KEY is not set; get a free key at fred.stlouisfed.org")
        self._api_key = api_key
        self._min_interval_s = min_interval_s
        self._last_request_at = 0.0
        self._http = httpx.Client(base_url=base_url, timeout=timeout_s, transport=transport)

    def __enter__(self) -> Self:
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        self.close()

    def close(self) -> None:
        self._http.close()

    def _throttle(self) -> None:
        wait = self._min_interval_s - (time.monotonic() - self._last_request_at)
        if wait > 0:
            time.sleep(wait)
        self._last_request_at = time.monotonic()

    @retry(
        retry=retry_if_exception(_is_retryable),
        wait=wait_random_exponential(multiplier=1, max=30),
        stop=stop_after_attempt(5),
        reraise=True,
    )
    def _get(self, path: str, params: dict[str, Any]) -> dict[str, Any]:
        self._throttle()
        response = self._http.get(
            path, params={**params, "api_key": self._api_key, "file_type": "json"}
        )
        if response.status_code == 400:
            # FRED explains bad requests (unknown series, bad key) in error_message.
            message = response.json().get("error_message", response.text)
            raise FredError(f"FRED rejected {path}: {message}")
        response.raise_for_status()
        body: dict[str, Any] = response.json()
        return body

    def get_series(self, series_id: str) -> SeriesMeta:
        body = self._get("/series", {"series_id": series_id})
        items = body.get("seriess") or []
        if not items:
            raise FredError(f"series {series_id} not found")
        s = items[0]
        obs_end = s.get("observation_end")
        return SeriesMeta(
            series_id=s["id"],
            title=s["title"],
            units=s.get("units"),
            frequency=s.get("frequency"),
            seasonal_adjustment=s.get("seasonal_adjustment"),
            notes=s.get("notes"),
            last_updated=parse_last_updated(s["last_updated"]),
            observation_end=date.fromisoformat(obs_end) if obs_end else None,
        )

    def get_observation_vintages(
        self, series_id: str, observation_start: date
    ) -> list[Observation]:
        """Every published value of every observation since `observation_start`."""
        observations: list[Observation] = []
        offset = 0
        while True:
            body = self._get(
                "/series/observations",
                {
                    "series_id": series_id,
                    "observation_start": observation_start.isoformat(),
                    "sort_order": "asc",
                    "limit": PAGE_LIMIT,
                    "offset": offset,
                    **ALL_REALTIME,
                },
            )
            page = body.get("observations", [])
            observations.extend(
                Observation(
                    obs_date=date.fromisoformat(o["date"]),
                    value=parse_value(o["value"]),
                    realtime_start=date.fromisoformat(o["realtime_start"]),
                )
                for o in page
            )
            offset += len(page)
            if not page or offset >= int(body.get("count", offset)):
                break
        log.debug("fred_observations_fetched", series_id=series_id, rows=len(observations))
        return observations
