from __future__ import annotations

import pandas as pd

from adzuna_etl.analysis.enrich import enrich_jobs_with_ai
from adzuna_etl.schema import CLEAN_SCHEMA
from adzuna_etl.warehouse import Warehouse, build_export_frames


NOT_TS = pd.Timestamp("2026-09-03T12:00:00Z")


def _clean_job(job_id: str, country: str = "gb") -> dict:
    row = {col: None for col in CLEAN_SCHEMA}
    row.update(
        {
            "job_id": job_id,
            "adref": f"adref-{job_id}",
            "title": "Data Engineer",
            "description": "Build ML pipelines with PyTorch and LLMs.",
            "company_name": "Acme",
            "salary_min": 60_000.0,
            "salary_max": 80_000.0,
            "salary_currency": "GBP",
            "salary_is_predicted": False,
            "location_display_name": "London",
            "location_area_0": "UK",
            "location_area_2": "London",
            "category_tag": "it-jobs",
            "category_label": "IT Jobs",
            "contract_type": "full_time",
            "contract_time": "permanent",
            "created_at": pd.Timestamp("2026-05-01T09:00:00Z"),
            "redirect_url": f"https://example.com/{job_id}",
            "source": "adzuna",
            "country": country,
            "ingested_at": NOT_TS,
            "ingest_date": "2026-09-03",
        }
    )
    return row


def test_warehouse_upserts_idempotently(tmp_path):
    clean = pd.DataFrame([_clean_job("j1"), _clean_job("j2")])
    analysis = enrich_jobs_with_ai(clean)

    db = Warehouse(tmp_path / "w.duckdb")
    db.upsert_jobs(clean)
    db.upsert_analysis(analysis)
    db.upsert_jobs(clean)      # same snapshot again -> replace, not duplicate
    db.upsert_analysis(analysis)

    assert db.table_count("fact_job_snapshot") == 2
    assert db.table_count("analysis_job_ai_flags") == 2
    frames = build_export_frames(db)
    assert set(frames) == {"ai_share_weekly", "ai_share_latest", "ai_skill_counts"}
    weekly = frames["ai_share_weekly"]
    assert not weekly.empty
    assert (weekly["role_class"] == "technical").all()
    assert float(weekly["ai_share"].iloc[0]) == 1.0
    db.close()
