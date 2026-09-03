"""CLEAN stage: normalise raw Adzuna ads into the canonical, DWH-ready schema.

Responsibilities: flatten nested objects, coerce types, clean text, parse UTC
timestamps, fix salary pairs, enforce the date window, and de-duplicate on the
snapshot natural key ``(job_id, ingest_date)``.
"""

from __future__ import annotations

import logging
import re
from datetime import datetime
from typing import Any, Optional

import pandas as pd

from adzuna_etl.config import Settings
from adzuna_etl.schema import CLEAN_SCHEMA

logger = logging.getLogger(__name__)

# Fallback currency per country when the API does not return one.
DEFAULT_CURRENCIES: dict[str, str] = {
    "gb": "GBP", "au": "AUD", "at": "EUR", "be": "EUR", "br": "BRL",
    "ca": "CAD", "ch": "CHF", "de": "EUR", "es": "EUR", "fr": "EUR",
    "id": "IDR", "in": "INR", "it": "EUR", "lu": "EUR", "mx": "MXN",
    "nl": "EUR", "nz": "NZD", "pl": "PLN", "sg": "SGD", "za": "ZAR",
}

_WS = re.compile(r"\s+")


def _clean_str(value: Any) -> Optional[str]:
    """Return a stripped, whitespace-collapsed string or None."""
    if value is None:
        return None
    if isinstance(value, float) and pd.isna(value):
        return None
    text = _WS.sub(" ", str(value)).strip()
    return text or None


def _to_float(value: Any) -> Optional[float]:
    """Coerce currencies/strings like '£32,500' to float, or None."""
    if value is None:
        return None
    try:
        if isinstance(value, str):
            value = value.replace(",", "").replace("£", "").replace("€", "").strip()
        number = float(value)
        return None if pd.isna(number) else number
    except (TypeError, ValueError):
        return None


def _norm_salary_pair(minimum: Any, maximum: Any) -> tuple[Optional[float], Optional[float]]:
    """Balance a salary pair: coerce, swap inverted pairs, fill missing half."""
    lo, hi = _to_float(minimum), _to_float(maximum)
    if lo is not None and hi is not None and lo > hi:
        lo, hi = hi, lo
    if lo is not None and hi is None:
        hi = lo
    if hi is not None and lo is None:
        lo = hi
    return lo, hi


def _norm_contract(value: Any) -> Optional[str]:
    """'Full_Time ' -> 'full_time' (normalise case, spaces, underscores)."""
    text = _clean_str(value)
    if text is None:
        return None
    return re.sub(r"\s+", "_", text.lower())


def _parse_dt(value: Any) -> Optional[pd.Timestamp]:
    """Parse an API timestamp to a tz-aware UTC pandas Timestamp, or None."""
    if value is None:
        return None
    ts = pd.to_datetime(value, utc=True, errors="coerce")
    return None if pd.isna(ts) else ts


def _flatten_ad(df_seen: dict[str, Any], ingested_at: datetime) -> dict[str, Any]:
    """Turn one raw API ad into one row of the canonical schema."""
    company = df_seen.get("company") or {}
    location = df_seen.get("location") or {}
    category = df_seen.get("category") or {}
    area = location.get("area") or []
    country = _clean_str(df_seen.get("country")) or ""

    salary_min, salary_max = _norm_salary_pair(
        df_seen.get("salary_min"), df_seen.get("salary_max")
    )
    created_at = _parse_dt(df_seen.get("created"))
    ingested = pd.Timestamp(ingested_at).tz_convert("UTC") if ingested_at.tzinfo else pd.Timestamp(ingested_at, tz="UTC")

    row = {
        "job_id": _clean_str(df_seen.get("id")),
        "adref": _clean_str(df_seen.get("adref")),
        "title": _clean_str(df_seen.get("title")),
        "description": _clean_str(df_seen.get("description")),
        "company_name": _clean_str(company.get("display_name")),
        "salary_min": salary_min,
        "salary_max": salary_max,
        "salary_currency": _clean_str(df_seen.get("salary_currency")) or DEFAULT_CURRENCIES.get(country, "GBP"),
        "salary_is_predicted": bool(int(df_seen.get("salary_is_predicted") or 0)),
        "location_display_name": _clean_str(location.get("display_name")),
        "location_area_0": _clean_str(area[0]) if len(area) > 0 else None,
        "location_area_1": _clean_str(area[1]) if len(area) > 1 else None,
        "location_area_2": _clean_str(area[2]) if len(area) > 2 else None,
        "latitude": _to_float(df_seen.get("latitude")),
        "longitude": _to_float(df_seen.get("longitude")),
        "category_tag": _clean_str(category.get("tag")),
        "category_label": _clean_str(category.get("label")),
        "contract_type": _norm_contract(df_seen.get("contract_type")),
        "contract_time": _norm_contract(df_seen.get("contract_time")),
        "created_at": created_at,
        "redirect_url": _clean_str(df_seen.get("redirect_url")),
        "source": "adzuna",
        "country": country,
        "ingested_at": ingested,
        "ingest_date": ingested.date().isoformat(),
    }
    return row


def clean_jobs(
    jobs: list[dict[str, Any]], settings: Settings, ingested_at: datetime
) -> tuple[pd.DataFrame, dict[str, int]]:
    """Clean raw ads into the canonical schema.

    Returns ``(df, report)`` where ``report`` counts what was removed.
    """
    report: dict[str, int] = {
        "input_rows": len(jobs),
        "missing_job_id_removed": 0,
        "duplicates_removed": 0,
        "outside_date_window_removed": 0,
        "output_rows": 0,
    }

    if not jobs:
        logger.warning("clean_jobs: no input rows; returning empty schema frame")
        return pd.DataFrame(columns=CLEAN_SCHEMA), report

    rows = [_flatten_ad(ad, ingested_at) for ad in jobs]
    df = pd.DataFrame(rows)

    # 1. Drop rows with no job id (nothing to key on).
    before = len(df)
    df = df[df["job_id"].notna() & (df["job_id"].astype(str).str.strip() != "")]
    report["missing_job_id_removed"] = before - len(df)

    # 2. De-duplicate identical snapshots of the same ad on the full natural
    #    key. Country is part of the key: Adzuna ids are globally unique, but
    #    never assume cross-country id collisions are the same snapshot.
    before = len(df)
    df = df.drop_duplicates(subset=["job_id", "country", "ingest_date"], keep="first")
    report["duplicates_removed"] = before - len(df)

    # 3. Enforce the date window (ads created before start_date are dropped).
    if settings.start_date:
        start = pd.Timestamp(settings.start_date, tz="UTC")
        before = len(df)
        df = df[df["created_at"].isna() | (df["created_at"] >= start)]
        report["outside_date_window_removed"] = before - len(df)

    # 4. Enforce the fixed schema (order + guarantees shown in schema.py).
    for col in CLEAN_SCHEMA:
        if col not in df.columns:
            df[col] = None
    df = df[CLEAN_SCHEMA]

    # 5. Type guarantees.
    df["salary_min"] = pd.to_numeric(df["salary_min"], errors="coerce")
    df["salary_max"] = pd.to_numeric(df["salary_max"], errors="coerce")
    df["latitude"] = pd.to_numeric(df["latitude"], errors="coerce")
    df["longitude"] = pd.to_numeric(df["longitude"], errors="coerce")
    df["salary_is_predicted"] = df["salary_is_predicted"].fillna(False).astype(bool)
    df["ingested_at"] = pd.to_datetime(df["ingested_at"], utc=True, errors="coerce")
    df["created_at"] = pd.to_datetime(df["created_at"], utc=True, errors="coerce")

    report["output_rows"] = len(df)
    logger.info(
        "clean_jobs: %d in -> %d out (no_id=%d, dup=%d, outside_window=%d)",
        report["input_rows"], report["output_rows"],
        report["missing_job_id_removed"], report["duplicates_removed"],
        report["outside_date_window_removed"],
    )
    return df, report


__all__ = ["clean_jobs", "DEFAULT_CURRENCIES", "CLEAN_SCHEMA"]