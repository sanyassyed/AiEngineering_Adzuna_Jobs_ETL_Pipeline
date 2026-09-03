from __future__ import annotations

from datetime import datetime, timezone

from adzuna_etl.clean import clean_jobs
from adzuna_etl.config import Settings
from adzuna_etl.schema import CLEAN_SCHEMA

INGESTED_AT = datetime(2026, 9, 3, 12, 0, tzinfo=timezone.utc)


def _ad(**overrides):
    """A minimal, valid Adzuna ad shaped like the real API response."""
    ad = {
        "id": "1610685200",
        "adref": "eyJ0eXBlIjoiYWR6IiwidCI6IjE2MTA2ODUyMDAifQ",
        "title": "Senior Data Engineer",
        "description": "Build and run ETL pipelines.",
        "company": {"display_name": "Acme Analytics Ltd"},
        "salary_min": 65000,
        "salary_max": 85000,
        "salary_is_predicted": 1,
        "created": "2026-07-15T09:30:00Z",
        "category": {"tag": "it-jobs", "label": "IT Jobs"},
        "location": {"area": ["UK", "Greater London", "London"], "display_name": "London"},
        "latitude": 51.509,
        "longitude": -0.118,
        "contract_type": "full_time",
        "contract_time": "permanent",
        "redirect_url": "https://www.adzuna.co.uk/land/ad/1610685200",
        "country": "gb",
    }
    ad.update(overrides)
    return ad


def _settings() -> Settings:
    return Settings(start_date="2026-01-01", data_dir="/tmp/adzuna-unused")


def test_clean_dedups_and_fixes_types():
    ads = [
        _ad(),
        _ad(),  # exact duplicate -> deduped
        _ad(id="1610685201", title="Junior Data Engineer", salary_min="£32,500",
            created="2026-08-01T08:00:00Z"),
        _ad(id="1610685202", company={"display_name": ""}, latitude=None,
            contract_type="Full_Time "),
    ]
    df, report = clean_jobs(ads, _settings(), INGESTED_AT)

    assert list(df.columns) == CLEAN_SCHEMA
    assert report["duplicates_removed"] == 1
    assert len(df) == 3
    assert df["salary_min"].iloc[1] == 32500.0
    assert df["contract_type"].iloc[2] == "full_time"
    assert df["title"].iloc[1] == "Junior Data Engineer"
    assert df["company_name"].iloc[2] is None  # empty string -> None
    assert df["created_at"].notna().all()
    assert df["created_at"].iloc[0].tz is not None
    assert df["ingest_date"].iloc[0] == "2026-09-03"
    assert df["country"].nunique() == 1


def test_clean_swaps_inverted_salary_pairs():
    ads = [_ad(id="swap-1", salary_min=90000, salary_max=70000)]
    df, _ = clean_jobs(ads, _settings(), INGESTED_AT)
    assert df["salary_min"].iloc[0] == 70000
    assert df["salary_max"].iloc[0] == 90000


def test_clean_filters_outside_date_window():
    ads = [
        _ad(),  # created 2026-07-15 -> kept
        _ad(id="old-1", created="2025-12-31T23:00:00Z"),  # before 2026-01-01 -> dropped
    ]
    df, report = clean_jobs(ads, _settings(), INGESTED_AT)
    assert report["outside_date_window_removed"] == 1
    assert len(df) == 1
    assert report["output_rows"] == 1


def test_clean_handles_empty_input():
    df, report = clean_jobs([], _settings(), INGESTED_AT)
    assert df.empty
    assert list(df.columns) == CLEAN_SCHEMA
    assert report["input_rows"] == 0


def test_currency_default_per_country():
    ads = [_ad(id="fr-1", country="fr")]
    df, _ = clean_jobs(ads, _settings(), INGESTED_AT)
    assert df["salary_currency"].iloc[0] == "EUR"