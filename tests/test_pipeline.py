from __future__ import annotations

from adzuna_etl.config import Settings
from adzuna_etl.pipeline import EtlPipeline


def test_mock_pipeline_end_to_end(tmp_path):
    settings = Settings(
        mock_mode=True,
        mock_rows=300,
        countries=["gb", "ie"],
        start_date="2026-01-01",
        data_dir=tmp_path,
    )
    result = EtlPipeline(settings).run()

    assert result.raw_jobs_count > 0
    assert result.cleaned_rows_count > 0
    assert result.raw_jobs_count > result.cleaned_rows_count  # dupes + window drops
    assert result.history_rows_count > 0
    assert result.validation.passed

    assert (tmp_path / "processed" / "adzuna_jobs_master.csv").exists()
    assert (tmp_path / "processed" / "adzuna_history_master.csv").exists()
    clean_partitions = list((tmp_path / "processed" / "jobs").glob("*_jobs_clean.csv"))
    assert len(clean_partitions) == 2  # one per country
    raw_json = list((tmp_path / "raw").glob("*/*_search.json"))
    assert len(raw_json) == 2

    # The master CSV is a valid clean-schema CSV we could load into a warehouse.
    import pandas as pd

    master = pd.read_csv(tmp_path / "processed" / "adzuna_jobs_master.csv")
    assert not master.empty
    assert set(master.columns) == {
        "job_id", "adref", "title", "description", "company_name", "salary_min",
        "salary_max", "salary_currency", "salary_is_predicted",
        "location_display_name", "location_area_0", "location_area_1",
        "location_area_2", "latitude", "longitude", "category_tag",
        "category_label", "contract_type", "contract_time", "created_at",
        "redirect_url", "source", "country", "ingested_at", "ingest_date",
    }
    assert master["ingest_date"].nunique() == 1  # single run = single partition


def test_settings_parses_comma_separated_countries():
    from adzuna_etl.config import Settings

    settings = Settings.model_validate({"countries": "gb,ie"})
    assert settings.countries == ["gb", "ie"]

    merged = Settings.model_validate({**settings.model_dump(), "countries": "gb"})
    assert merged.countries == ["gb"]


def test_pipeline_requires_credentials_for_live_mode():
    from adzuna_etl.api_client import AdzunaApiError

    settings = Settings(data_dir="/tmp/adz-x")  # no credentials
    pipeline = EtlPipeline(settings)
    try:
        pipeline._build_client()
    except AdzunaApiError:
        pass
    else:  # pragma: no cover
        raise AssertionError("expected AdzunaApiError for missing credentials")