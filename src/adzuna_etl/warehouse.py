"""DuckDB warehouse for phase 1.

Stores two tables on disk:
  * ``fact_job_snapshot``     - the cleaned snapshot rows (CSV contract)
  * ``analysis_job_ai_flags`` - the AI-skills/role analysis flags per snapshot
Both are keyed by the snapshot natural key ``(job_id, country, ingest_date)``
and loaded idempotently (INSERT OR REPLACE), so re-runs never duplicate rows.

Convenience views drive the Google Sheets / Looker Studio export.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import duckdb
import pandas as pd

from adzuna_etl.analysis.enrich import ANALYSIS_COLUMNS
from adzuna_etl.schema import CLEAN_SCHEMA

FACT_TABLE = "fact_job_snapshot"
ANALYSIS_TABLE = "analysis_job_ai_flags"

_FACT_DDL = f"""
CREATE TABLE IF NOT EXISTS {FACT_TABLE} (
    job_id                VARCHAR NOT NULL,
    adref                 VARCHAR,
    title                 VARCHAR,
    description           VARCHAR,
    company_name          VARCHAR,
    salary_min            DOUBLE,
    salary_max            DOUBLE,
    salary_currency       VARCHAR,
    salary_is_predicted   BOOLEAN,
    location_display_name VARCHAR,
    location_area_0       VARCHAR,
    location_area_1       VARCHAR,
    location_area_2       VARCHAR,
    latitude              DOUBLE,
    longitude             DOUBLE,
    category_tag          VARCHAR,
    category_label        VARCHAR,
    contract_type         VARCHAR,
    contract_time         VARCHAR,
    created_at            TIMESTAMPTZ,
    redirect_url          VARCHAR,
    source                VARCHAR,
    country               VARCHAR NOT NULL,
    ingested_at           TIMESTAMPTZ,
    ingest_date           VARCHAR NOT NULL,
    PRIMARY KEY (job_id, country, ingest_date)
)
"""

_ANALYSIS_DDL = f"""
CREATE TABLE IF NOT EXISTS {ANALYSIS_TABLE} (
    job_id                VARCHAR NOT NULL,
    country               VARCHAR NOT NULL,
    ingest_date           VARCHAR NOT NULL,
    created_at            TIMESTAMPTZ,
    title                 VARCHAR,
    description           VARCHAR,
    category_tag          VARCHAR,
    category_label        VARCHAR,
    role_class            VARCHAR,
    ai_mentioned          BOOLEAN,
    ai_total_mentions     BIGINT,
    ai_general_ai         BIGINT,
    ai_machine_learning   BIGINT,
    ai_ml_tools           BIGINT,
    ai_generative_ai      BIGINT,
    taxonomy_version      VARCHAR,
    role_classifier_version VARCHAR,
    PRIMARY KEY (job_id, country, ingest_date)
)
"""

_VIEWS: dict[str, str] = {
    "v_ai_share_weekly": f"""
        CREATE OR REPLACE VIEW v_ai_share_weekly AS
        SELECT
            CAST(date_trunc('week', f.created_at) AS DATE) AS week,
            f.country                                        AS country,
            a.role_class                                     AS role_class,
            COUNT(*)                                         AS total_ads,
            SUM(CASE WHEN a.ai_mentioned THEN 1 ELSE 0 END)  AS ai_ads,
            ROUND(AVG(CASE WHEN a.ai_mentioned THEN 1.0 ELSE 0.0 END), 4) AS ai_share
        FROM {FACT_TABLE} f
        JOIN {ANALYSIS_TABLE} a USING (job_id, country, ingest_date)
        GROUP BY 1, 2, 3
    """,
    "v_ai_share_latest": f"""
        CREATE OR REPLACE VIEW v_ai_share_latest AS
        SELECT * FROM v_ai_share_weekly
        WHERE week = (SELECT MAX(week) FROM v_ai_share_weekly)
    """,
    "v_ai_skill_counts": f"""
        CREATE OR REPLACE VIEW v_ai_skill_counts AS
        SELECT
            country,
            role_class,
            SUM(ai_general_ai)       AS general_ai_mentions,
            SUM(ai_machine_learning) AS machine_learning_mentions,
            SUM(ai_ml_tools)         AS ml_tools_mentions,
            SUM(ai_generative_ai)    AS generative_ai_mentions,
            COUNT(*)                 AS ads
        FROM {ANALYSIS_TABLE}
        GROUP BY country, role_class
    """,
}


def _normalise_columns(df: pd.DataFrame, schema: list[str]) -> pd.DataFrame:
    for col in schema:
        if col not in df.columns:
            df[col] = None
    return df[schema]


class Warehouse:
    """Thin, idempotent wrapper around a DuckDB database file."""

    def __init__(self, path: Path | str) -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.conn = duckdb.connect(str(self.path))
        self.ensure_schema()

    def ensure_schema(self) -> None:
        self.conn.execute(_FACT_DDL)
        self.conn.execute(_ANALYSIS_DDL)
        for view_sql in _VIEWS.values():
            self.conn.execute(view_sql)

    def upsert_jobs(self, clean_df: pd.DataFrame) -> int:
        """Idempotently load cleaned snapshot rows."""
        if clean_df.empty:
            return 0
        frame = _normalise_columns(clean_df.copy(), CLEAN_SCHEMA)
        self.conn.register("dw_clean", frame)
        self.conn.execute(f"INSERT OR REPLACE INTO {FACT_TABLE} SELECT * FROM dw_clean")
        self.conn.unregister("dw_clean")
        return len(frame)

    def upsert_analysis(self, analysis_df: pd.DataFrame) -> int:
        """Idempotently load the AI-analysis flags."""
        if analysis_df.empty:
            return 0
        frame = _normalise_columns(analysis_df.copy(), ANALYSIS_COLUMNS)
        self.conn.register("dw_ai", frame)
        self.conn.execute(f"INSERT OR REPLACE INTO {ANALYSIS_TABLE} SELECT * FROM dw_ai")
        self.conn.unregister("dw_ai")
        return len(frame)

    def query(self, sql: str) -> pd.DataFrame:
        return self.conn.execute(sql).df()

    def table_count(self, table: str) -> int:
        return int(self.conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0])

    def close(self) -> None:
        self.conn.close()

    def __enter__(self) -> "Warehouse":
        return self

    def __exit__(self, *exc_info: Any) -> None:
        self.close()


def build_export_frames(warehouse: Warehouse) -> dict[str, pd.DataFrame]:
    """Pull the views used by the Google Sheets / Looker Studio export."""
    return {
        "ai_share_weekly": warehouse.query(
            "SELECT * FROM v_ai_share_weekly ORDER BY week, country, role_class"
        ),
        "ai_share_latest": warehouse.query(
            "SELECT * FROM v_ai_share_latest ORDER BY ai_share DESC"
        ),
        "ai_skill_counts": warehouse.query(
            "SELECT * FROM v_ai_skill_counts ORDER BY ads DESC"
        ),
    }


__all__ = ["ANALYSIS_TABLE", "FACT_TABLE", "Warehouse", "build_export_frames"]
