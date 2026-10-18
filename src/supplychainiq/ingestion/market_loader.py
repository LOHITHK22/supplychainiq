"""Publication-aware incremental loading of public market series.

For each series:
1. Record an `ops.ingestion_run` row ('running') in its own transaction, so failures
   are visible even if the load rolls back.
2. Compare the publisher's `last_updated` with `ops.source_watermark`.
   Not newer -> status 'no_new_release'; nothing else is touched.
3. Newer -> fetch all vintages, append unseen rows to `raw.market_observation`
   (ON CONFLICT DO NOTHING keeps the load idempotent), refresh series metadata,
   advance the watermark, record lineage, mark the run 'loaded' — all in one transaction.

Usage:  uv run python -m supplychainiq.ingestion.market_loader
"""

import uuid
from dataclasses import dataclass
from datetime import date, datetime
from typing import Literal, Protocol

from sqlalchemy import Connection, Engine, text

from supplychainiq.ingestion.catalog import FRED_SERIES, OBSERVATION_START
from supplychainiq.ingestion.fred import Observation, SeriesMeta
from supplychainiq.log import get_logger

SOURCE = "fred"
log = get_logger(__name__)

Status = Literal["loaded", "no_new_release", "failed"]


class MarketSource(Protocol):
    def get_series(self, series_id: str) -> SeriesMeta: ...
    def get_observation_vintages(
        self, series_id: str, observation_start: date
    ) -> list[Observation]: ...


@dataclass(frozen=True)
class IngestResult:
    series_id: str
    status: Status
    rows_fetched: int = 0
    rows_inserted: int = 0
    error: str | None = None


def _start_run(conn: Connection, run_id: uuid.UUID, series_id: str) -> uuid.UUID:
    return uuid.UUID(
        str(
            conn.execute(
                text(
                    """
                    INSERT INTO ops.ingestion_run (run_id, source, series_id, status)
                    VALUES (:run_id, :source, :series_id, 'running')
                    RETURNING ingestion_run_id
                    """
                ),
                {"run_id": run_id, "source": SOURCE, "series_id": series_id},
            ).scalar_one()
        )
    )


def _finish_run(
    conn: Connection, ingestion_run_id: uuid.UUID, result: IngestResult, meta: SeriesMeta | None
) -> None:
    conn.execute(
        text(
            """
            UPDATE ops.ingestion_run
               SET status = :status, rows_fetched = :fetched, rows_inserted = :inserted,
                   source_last_updated = :last_updated, error_message = :error,
                   finished_at = now()
             WHERE ingestion_run_id = :id
            """
        ),
        {
            "status": result.status,
            "fetched": result.rows_fetched,
            "inserted": result.rows_inserted,
            "last_updated": meta.last_updated if meta else None,
            "error": result.error,
            "id": ingestion_run_id,
        },
    )


def _watermark(conn: Connection, series_id: str) -> datetime | None:
    value: datetime | None = conn.execute(
        text(
            "SELECT last_updated FROM ops.source_watermark "
            "WHERE source = :source AND series_id = :series_id"
        ),
        {"source": SOURCE, "series_id": series_id},
    ).scalar_one_or_none()
    return value


def _load(
    conn: Connection,
    run_id: uuid.UUID,
    ingestion_run_id: uuid.UUID,
    meta: SeriesMeta,
    observations: list[Observation],
) -> int:
    inserted = 0
    if observations:
        rows = [
            {
                "source": SOURCE,
                "series_id": meta.series_id,
                "obs_date": o.obs_date,
                "value": o.value,
                "realtime_start": o.realtime_start,
                "ingestion_run_id": ingestion_run_id,
            }
            for o in observations
        ]
        before = conn.execute(
            text(
                "SELECT count(*) FROM raw.market_observation "
                "WHERE source = :source AND series_id = :series_id"
            ),
            {"source": SOURCE, "series_id": meta.series_id},
        ).scalar_one()
        conn.execute(
            text(
                """
                INSERT INTO raw.market_observation
                    (source, series_id, obs_date, value, realtime_start, ingestion_run_id)
                VALUES (:source, :series_id, :obs_date, :value, :realtime_start,
                        :ingestion_run_id)
                ON CONFLICT (source, series_id, obs_date, realtime_start) DO NOTHING
                """
            ),
            rows,
        )
        after = conn.execute(
            text(
                "SELECT count(*) FROM raw.market_observation "
                "WHERE source = :source AND series_id = :series_id"
            ),
            {"source": SOURCE, "series_id": meta.series_id},
        ).scalar_one()
        inserted = int(after) - int(before)

    conn.execute(
        text(
            """
            INSERT INTO raw.market_series (source, series_id, title, units, frequency,
                seasonal_adjustment, notes, source_last_updated)
            VALUES (:source, :series_id, :title, :units, :frequency, :sa, :notes, :lu)
            ON CONFLICT (source, series_id) DO UPDATE SET
                title = EXCLUDED.title, units = EXCLUDED.units,
                frequency = EXCLUDED.frequency,
                seasonal_adjustment = EXCLUDED.seasonal_adjustment,
                notes = EXCLUDED.notes, source_last_updated = EXCLUDED.source_last_updated,
                fetched_at = now()
            """
        ),
        {
            "source": SOURCE,
            "series_id": meta.series_id,
            "title": meta.title,
            "units": meta.units,
            "frequency": meta.frequency,
            "sa": meta.seasonal_adjustment,
            "notes": meta.notes,
            "lu": meta.last_updated,
        },
    )
    conn.execute(
        text(
            """
            INSERT INTO ops.source_watermark
                (source, series_id, last_updated, last_observation_date)
            VALUES (:source, :series_id, :lu, :last_obs)
            ON CONFLICT (source, series_id) DO UPDATE SET
                last_updated = EXCLUDED.last_updated,
                last_observation_date = EXCLUDED.last_observation_date,
                updated_at = now()
            """
        ),
        {
            "source": SOURCE,
            "series_id": meta.series_id,
            "lu": meta.last_updated,
            "last_obs": max((o.obs_date for o in observations), default=None),
        },
    )
    conn.execute(
        text(
            """
            INSERT INTO ops.lineage_edge (run_id, from_node, to_node, rows_moved)
            VALUES (:run_id, :from_node, 'raw.market_observation', :rows)
            ON CONFLICT (run_id, from_node, to_node)
            DO UPDATE SET rows_moved = EXCLUDED.rows_moved
            """
        ),
        {"run_id": run_id, "from_node": f"{SOURCE}:{meta.series_id}", "rows": inserted},
    )
    return inserted


def ingest_series(
    engine: Engine,
    source: MarketSource,
    series_id: str,
    run_id: uuid.UUID,
    observation_start: date = OBSERVATION_START,
) -> IngestResult:
    bound = log.bind(run_id=str(run_id), source=SOURCE, series_id=series_id)
    with engine.begin() as conn:
        ingestion_run_id = _start_run(conn, run_id, series_id)

    meta: SeriesMeta | None = None
    try:
        meta = source.get_series(series_id)
        with engine.begin() as conn:
            known = _watermark(conn, series_id)
            if known is not None and meta.last_updated <= known:
                result = IngestResult(series_id, "no_new_release")
                _finish_run(conn, ingestion_run_id, result, meta)
                bound.info("no_new_release", last_updated=meta.last_updated.isoformat())
                return result

        observations = source.get_observation_vintages(series_id, observation_start)
        with engine.begin() as conn:
            inserted = _load(conn, run_id, ingestion_run_id, meta, observations)
            result = IngestResult(series_id, "loaded", len(observations), inserted)
            _finish_run(conn, ingestion_run_id, result, meta)
        bound.info("loaded", rows_fetched=len(observations), rows_inserted=inserted)
        return result
    except Exception as exc:  # recorded, then the caller decides whether to continue
        result = IngestResult(series_id, "failed", error=f"{type(exc).__name__}: {exc}")
        with engine.begin() as conn:
            _finish_run(conn, ingestion_run_id, result, meta)
        bound.error("ingest_failed", error=result.error)
        return result


def ingest_all(
    engine: Engine,
    source: MarketSource,
    run_id: uuid.UUID | None = None,
    series_ids: list[str] | None = None,
) -> list[IngestResult]:
    """Ingest every catalogue series; one failure does not stop the others."""
    run_id = run_id or uuid.uuid4()
    ids = series_ids or [s.series_id for s in FRED_SERIES]
    return [ingest_series(engine, source, sid, run_id) for sid in ids]


if __name__ == "__main__":
    from supplychainiq.config import get_settings
    from supplychainiq.db import get_engine
    from supplychainiq.ingestion.fred import FredClient
    from supplychainiq.log import configure_logging

    configure_logging()
    settings = get_settings()
    with FredClient(settings.fred_api_key.get_secret_value()) as client:
        results = ingest_all(get_engine("ingest"), client)
    for r in results:
        log.info(
            "summary",
            series_id=r.series_id,
            status=r.status,
            rows_fetched=r.rows_fetched,
            rows_inserted=r.rows_inserted,
            error=r.error,
        )
    raise SystemExit(1 if any(r.status == "failed" for r in results) else 0)
