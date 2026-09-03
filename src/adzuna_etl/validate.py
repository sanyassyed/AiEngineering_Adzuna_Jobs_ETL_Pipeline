"""VALIDATE stage: automated data-quality checks on the cleaned frame.

Each check records PASS / WARN / FAIL. A FAIL means the data should not be
loaded to a warehouse as-is; the pipeline can be told to hard-stop on FAIL
via ``ADZUNA_FAIL_ON_VALIDATION=true``.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import pandas as pd

from adzuna_etl.config import Settings
from adzuna_etl.schema import CLEAN_SCHEMA


@dataclass
class ValidationReport:
    passed: bool
    checks: list[dict[str, str]] = field(default_factory=list)
    null_summary: pd.DataFrame = field(default_factory=pd.DataFrame)


def _check(name: str, status: str, detail: Any) -> dict[str, str]:
    return {"name": name, "status": status, "detail": str(detail)}


def validate_jobs(df: pd.DataFrame, settings: Settings) -> ValidationReport:
    """Run the QA battery against a cleaned jobs frame."""
    checks: list[dict[str, str]] = []

    missing_cols = [c for c in CLEAN_SCHEMA if c not in df.columns]
    checks.append(_check(
        "schema_columns",
        "FAIL" if missing_cols else "PASS",
        f"{len(df.columns)} columns; missing={missing_cols or 'none'}",
    ))

    if df.empty:
        checks.append(_check("row_count", "WARN", "dataset is empty; nothing to validate"))
        return ValidationReport(passed=False, checks=checks)

    nulls = df.isna().mean().sort_values(ascending=False)
    null_summary = pd.DataFrame({"column": nulls.index, "null_rate": nulls.values})

    dupes = int(df.duplicated(subset=["job_id", "country", "ingest_date"]).sum())
    checks.append(_check(
        "duplicate_snapshots",
        "PASS" if dupes == 0 else "FAIL",
        f"{dupes} duplicate (job_id, country, ingest_date) rows",
    ))

    empty_id = int(df["job_id"].isna().sum())
    checks.append(_check(
        "missing_job_id", "PASS" if empty_id == 0 else "FAIL",
        f"{empty_id} rows without a job_id",
    ))

    if settings.start_date:
        start = pd.Timestamp(settings.start_date, tz="UTC")
        created = df["created_at"].dropna()
        outside = int((created < start).sum())
        checks.append(_check(
            "created_window",
            "WARN" if outside else "PASS",
            f"{outside} rows created before {settings.start_date}",
        ))
    future = int((df["created_at"].dropna() > pd.Timestamp.now(tz="UTC")).sum())
    checks.append(_check(
        "future_dates", "WARN" if future else "PASS",
        f"{future} rows created in the future",
    ))

    salary = df[["salary_min", "salary_max"]].dropna()
    inverted = int((salary["salary_min"] > salary["salary_max"]).sum())
    checks.append(_check(
        "salary_order",
        "PASS" if inverted == 0 else "WARN",
        f"{inverted} rows where salary_min > salary_max",
    ))

    bad_lat = int((df["latitude"].fillna(0).abs() > 90).sum())
    bad_lon = int((df["longitude"].fillna(0).abs() > 180).sum())
    checks.append(_check(
        "coordinates",
        "PASS" if bad_lat + bad_lon == 0 else "FAIL",
        f"{bad_lat} bad latitudes, {bad_lon} bad longitudes",
    ))

    for col in ("title", "created_at"):
        rate = float(nulls.get(col, 0.0) or 0.0)
        checks.append(_check(
            f"null_{col}",
            "WARN" if rate > 0 else "PASS",
            f"null rate {rate:.1%}",
        ))

    passed = all(c["status"] != "FAIL" for c in checks)
    return ValidationReport(passed=passed, checks=checks, null_summary=null_summary)


__all__ = ["ValidationReport", "validate_jobs"]