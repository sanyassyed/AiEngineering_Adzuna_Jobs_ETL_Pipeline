"""LOAD stage: persist raw + cleaned data to CSV with atomic writes.

Layout (all under ``data_dir``)::

    raw/{ingest_date}/{country}_search.json        full paginated API payloads
    raw/{ingest_date}/{country}_search_raw.csv      flattened raw ads
    raw/{ingest_date}/{country}_history.json        raw history payload
    raw/{ingest_date}/{country}_history_raw.csv     normalised history rows
    processed/jobs/{ingest_date}_{country}_jobs_clean.csv   incremental delta
    processed/history/{ingest_date}_{country}_history.csv   incremental delta
    processed/adzuna_jobs_master.csv                        accumulated snapshots
    processed/adzuna_history_master.csv                     accumulated history

The ``processed/jobs`` partition files are the natural boundaries for the
future data-warehouse loader: every run emits one CSV per country that is the
exact delta to ingest incrementally.
"""

from __future__ import annotations

import json
import logging
import os
from pathlib import Path
from typing import Any

import pandas as pd

from adzuna_etl.config import Settings
from adzuna_etl.extract import ExtractionResult
from adzuna_etl.schema import CLEAN_SCHEMA, HISTORY_SCHEMA

logger = logging.getLogger(__name__)


def flatten_raw(ad: dict[str, Any]) -> dict[str, Any]:
    """One-row flatten of a raw ad; nested objects kept as JSON for fidelity."""
    row: dict[str, Any] = {}
    for key, value in ad.items():
        if isinstance(value, (dict, list)):
            row[key] = json.dumps(value, ensure_ascii=False, default=str)
        else:
            row[key] = value
    return row


def _atomic_write_df(df: pd.DataFrame, path: Path) -> None:
    """Write a CSV atomically (tmp file + rename) so a crash never truncates."""
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".tmp")
    df.to_csv(tmp, index=False)
    os.replace(tmp, path)


def _write_json(payload: Any, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".tmp")
    with open(tmp, "w", encoding="utf-8") as handle:
        json.dump(payload, handle, ensure_ascii=False, default=str, indent=2)
    os.replace(tmp, path)


class CsvLoader:
    """Writes extraction + cleaned results into the layered CSV layout."""

    def __init__(self, settings: Settings) -> None:
        self.settings = settings

    def save_all(
        self, extraction: ExtractionResult, clean_df: pd.DataFrame
    ) -> list[str]:
        written: list[str] = []
        ingest_date = extraction.ingested_at.date().isoformat()

        for country, responses in extraction.search_responses.items():
            written.extend(
                self._save_raw_country(country, ingest_date, responses, extraction)
            )
            written.append(self._save_clean_partition(country, ingest_date, clean_df))

        written.extend(self._save_masters(extraction, clean_df))
        logger.info("LOAD complete: %d files written", len(written))
        return written

    # -- raw layer ---------------------------------------------------------------
    def _save_raw_country(
        self,
        country: str,
        ingest_date: str,
        responses: list[dict[str, Any]],
        extraction: ExtractionResult,
    ) -> list[str]:
        raw_dir = self.settings.raw_dir / ingest_date
        written: list[str] = []

        payload_path = raw_dir / f"{country}_search.json"
        _write_json({"responses": responses}, payload_path)
        written.append(str(payload_path))

        ads = [ad for ad in extraction.jobs if ad.get("country") == country]
        flat = pd.DataFrame([flatten_raw(ad) for ad in ads])
        ads_path = raw_dir / f"{country}_search_raw.csv"
        _atomic_write_df(flat, ads_path)
        written.append(str(ads_path))

        history_payload = extraction.history_responses.get(country)
        if history_payload is not None:
            hist_json = raw_dir / f"{country}_history.json"
            _write_json(history_payload, hist_json)
            written.append(str(hist_json))

        hist_rows = [h for h in extraction.history if h.get("country") == country]
        hist_csv = raw_dir / f"{country}_history_raw.csv"
        _atomic_write_df(_to_history_frame(hist_rows), hist_csv)
        written.append(str(hist_csv))
        return written

    # -- clean layer --------------------------------------------------------------
    def _save_clean_partition(
        self, country: str, ingest_date: str, clean_df: pd.DataFrame
    ) -> str:
        subset = clean_df[clean_df["country"] == country] if not clean_df.empty else clean_df
        path = self.settings.jobs_dir / f"{ingest_date}_{country}_jobs_clean.csv"
        _atomic_write_df(subset[CLEAN_SCHEMA] if not subset.empty else subset, path)
        return str(path)

    # -- masters ------------------------------------------------------------------
    def _save_masters(
        self, extraction: ExtractionResult, clean_df: pd.DataFrame
    ) -> list[str]:
        written: list[str] = []

        job_master = self.settings.processed_dir / "adzuna_jobs_master.csv"
        _upsert_master(
            clean_df, job_master,
            key=["job_id", "country", "ingest_date"],
            sort_by=["ingest_date", "created_at", "job_id"],
        )
        written.append(str(job_master))

        hist_df = _to_history_frame(extraction.history)
        hist_master = self.settings.processed_dir / "adzuna_history_master.csv"
        _upsert_master(hist_df, hist_master, key=["country", "day"], sort_by=["day"])
        written.append(str(hist_master))
        return written


def _to_history_frame(rows: list[dict[str, Any]]) -> pd.DataFrame:
    df = pd.DataFrame(rows)
    if df.empty:
        return pd.DataFrame(columns=HISTORY_SCHEMA)
    for col in HISTORY_SCHEMA:
        if col not in df.columns:
            df[col] = None
    return df[HISTORY_SCHEMA]


def _upsert_master(
    new_df: pd.DataFrame,
    path: Path,
    key: list[str],
    sort_by: list[str],
) -> None:
    """Merge a new batch into an accumulated master CSV (dedup on ``key``)."""
    if path.exists() and path.stat().st_size > 0 and not new_df.empty:
        previous = pd.read_csv(path)
        combined = pd.concat([previous, new_df], ignore_index=True)
    else:
        combined = new_df
    if not combined.empty:
        combined = combined.drop_duplicates(subset=key, keep="last")
        combined = combined.sort_values(sort_by, na_position="last")
    _atomic_write_df(combined, path)


__all__ = ["CsvLoader", "flatten_raw"]