"""Canonical schemas shared across the pipeline.

``CLEAN_SCHEMA`` is the contract emitted by the cleaning layer and consumed by
validation, EDA, and - in the future - the data-warehouse loader. Every run
produces exactly these columns, in this order, so downstream consumers never
depend on Adzuna API field drift.

Design notes for the future warehouse (SCD Type 2 / incremental):
  * (job_id, country, ingest_date) is the natural key of a *snapshot* row:
    the same job_id across two ingest dates is two observable states, which
    is exactly what SCD Type 2 needs (valid_from / valid_to windows).
  * ``job_id`` + ``adref`` are the stable business keys for the job dimension.
  * ``company_name``, ``category_*``, ``location_*`` and ``contract_*`` are
    natural keys for candidate dimensions (company, category, location, job).
"""

from __future__ import annotations

CLEAN_SCHEMA: list[str] = [
    "job_id",                # Adzuna ad id (part of the snapshot natural key)
    "adref",                 # Adzuna reference token (stable business key)
    "title",
    "description",
    "company_name",
    "salary_min",
    "salary_max",
    "salary_currency",
    "salary_is_predicted",
    "location_display_name",
    "location_area_0",       # most general area (e.g. country/region)
    "location_area_1",       # intermediate area (e.g. county)
    "location_area_2",       # most specific area (e.g. town)
    "latitude",
    "longitude",
    "category_tag",
    "category_label",
    "contract_type",         # full_time / part_time
    "contract_time",         # permanent / contract
    "created_at",            # when the ad was created (UTC, tz-aware)
    "redirect_url",
    "source",                # 'adzuna'
    "country",               # ISO country code the ad was pulled from
    "ingested_at",           # when this snapshot was pulled (UTC)
    "ingest_date",           # YYYY-MM-DD partition of the snapshot
]

HISTORY_SCHEMA: list[str] = [
    "country",
    "day",       # YYYY-MM-DD
    "count",     # aggregate vacancies on that day
    "details_json",  # full per-day payload from the API (fidelity)
]

__all__ = ["CLEAN_SCHEMA", "HISTORY_SCHEMA"]