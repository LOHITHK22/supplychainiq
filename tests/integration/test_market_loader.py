"""Publication-aware loading against a real PostgreSQL test database.

A fake source stands in for FRED so each scenario (first load, no new release,
revision, failure) is deterministic and needs no API key.
"""

import uuid
from dataclasses import dataclass, field, replace
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal

import pytest
from sqlalchemy import Engine, text

from supplychainiq.ingestion.fred import Observation, SeriesMeta
from supplychainiq.ingestion.market_loader import ingest_all, ingest_series

pytestmark = pytest.mark.integration

CT = timezone(timedelta(hours=-5))


@dataclass
class FakeSource:
    meta: SeriesMeta
    observations: list[Observation]
    fail_with: Exception | None = None
    observation_calls: int = field(default=0)

    def get_series(self, series_id: str) -> SeriesMeta:
        if self.fail_with:
            raise self.fail_with
        return self.meta

    def get_observation_vintages(
        self, series_id: str, observation_start: date
    ) -> list[Observation]:
        self.observation_calls += 1
        return self.observations


def meta(last_updated: datetime) -> SeriesMeta:
    return SeriesMeta(
        "RSNSR",
        "Advance Retail Sales: Nonstore Retailers",
        "Millions of Dollars",
        "Monthly",
        "Seasonally Adjusted",
        None,
        last_updated,
        date(2026, 8, 1),
    )


FIRST = [
    Observation(date(2026, 7, 1), Decimal("120000"), date(2026, 8, 14)),
    Observation(date(2026, 8, 1), Decimal("121000"), date(2026, 9, 16)),
]


def count(engine: Engine, sql: str) -> int:
    with engine.connect() as conn:
        return int(conn.execute(text(sql)).scalar_one())


def test_first_load_inserts_and_records_metadata(engine: Engine) -> None:
    source = FakeSource(meta(datetime(2026, 9, 16, 7, 30, tzinfo=CT)), FIRST)
    result = ingest_series(engine, source, "RSNSR", uuid.uuid4())

    assert (result.status, result.rows_fetched, result.rows_inserted) == ("loaded", 2, 2)
    assert count(engine, "SELECT count(*) FROM raw.market_observation") == 2
    assert count(engine, "SELECT count(*) FROM ops.source_watermark") == 1
    assert count(engine, "SELECT count(*) FROM ops.lineage_edge WHERE rows_moved = 2") == 1
    assert count(engine, "SELECT count(*) FROM ops.ingestion_run WHERE status='loaded'") == 1


def test_unchanged_release_is_skipped_without_touching_data(engine: Engine) -> None:
    source = FakeSource(meta(datetime(2026, 9, 16, 7, 30, tzinfo=CT)), FIRST)
    ingest_series(engine, source, "RSNSR", uuid.uuid4())

    second = ingest_series(engine, source, "RSNSR", uuid.uuid4())

    assert second.status == "no_new_release"
    assert source.observation_calls == 1  # observations were not even downloaded again
    assert count(engine, "SELECT count(*) FROM raw.market_observation") == 2
    assert (
        count(engine, "SELECT count(*) FROM ops.ingestion_run WHERE status='no_new_release'") == 1
    )


def test_revision_appends_a_new_vintage_and_keeps_the_old_one(engine: Engine) -> None:
    source = FakeSource(meta(datetime(2026, 9, 16, 7, 30, tzinfo=CT)), FIRST)
    ingest_series(engine, source, "RSNSR", uuid.uuid4())

    revised = [
        *FIRST,
        Observation(date(2026, 8, 1), Decimal("121500"), date(2026, 10, 15)),  # revision
        Observation(date(2026, 9, 1), Decimal("122000"), date(2026, 10, 15)),  # new month
    ]
    source = replace(
        source, meta=meta(datetime(2026, 10, 15, 7, 30, tzinfo=CT)), observations=revised
    )
    result = ingest_series(engine, source, "RSNSR", uuid.uuid4())

    assert (result.status, result.rows_fetched, result.rows_inserted) == ("loaded", 4, 2)
    with engine.connect() as conn:
        aug = (
            conn.execute(
                text(
                    "SELECT value FROM raw.market_observation WHERE obs_date = '2026-08-01' "
                    "ORDER BY realtime_start"
                )
            )
            .scalars()
            .all()
        )
    assert aug == [Decimal("121000"), Decimal("121500")]


def test_rerunning_the_same_release_is_idempotent(engine: Engine) -> None:
    source = FakeSource(meta(datetime(2026, 9, 16, 7, 30, tzinfo=CT)), FIRST)
    ingest_series(engine, source, "RSNSR", uuid.uuid4())
    # Simulate a crash after loading but before the watermark advanced.
    with engine.begin() as conn:
        conn.execute(text("DELETE FROM ops.source_watermark"))

    again = ingest_series(engine, source, "RSNSR", uuid.uuid4())

    assert (again.status, again.rows_inserted) == ("loaded", 0)
    assert count(engine, "SELECT count(*) FROM raw.market_observation") == 2


def test_failure_is_recorded_and_other_series_continue(engine: Engine) -> None:
    good = FakeSource(meta(datetime(2026, 9, 16, 7, 30, tzinfo=CT)), FIRST)
    bad = FakeSource(good.meta, [], fail_with=ConnectionError("FRED unreachable"))

    class Router:
        def get_series(self, series_id: str) -> SeriesMeta:
            return (bad if series_id == "BROKEN" else good).get_series(series_id)

        def get_observation_vintages(self, series_id: str, start: date) -> list[Observation]:
            return good.get_observation_vintages(series_id, start)

    results = ingest_all(engine, Router(), series_ids=["BROKEN", "RSNSR"])

    assert [r.status for r in results] == ["failed", "loaded"]
    assert "FRED unreachable" in (results[0].error or "")
    with engine.connect() as conn:
        status, err, finished = conn.execute(
            text(
                "SELECT status, error_message, finished_at FROM ops.ingestion_run "
                "WHERE series_id = 'BROKEN'"
            )
        ).one()
    assert status == "failed" and "ConnectionError" in err and finished is not None


def test_raw_history_cannot_be_rewritten_by_the_pipeline_role(engine: Engine) -> None:
    ingest_series(
        engine, FakeSource(meta(datetime(2026, 9, 16, tzinfo=CT)), FIRST), "RSNSR", uuid.uuid4()
    )
    with pytest.raises(Exception, match="permission denied"), engine.begin() as conn:
        conn.execute(text("UPDATE raw.market_observation SET value = 0"))
