"""Runtime configuration, loaded from environment variables / ``.env``.

All settings are prefixed with ``ADZUNA_`` (e.g. ``ADZUNA_APP_ID``).
Fields map 1:1 to the ``.env.example`` file committed in the repo root.
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Annotated

from pydantic import Field, field_validator
from pydantic_settings import NoDecode, BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Runtime configuration for the adzuna-etl pipeline."""

    model_config = SettingsConfigDict(
        env_prefix="ADZUNA_",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # --- Adzuna credentials -------------------------------------------------
    app_id: str = ""
    app_key: str = ""

    # --- Extraction ----------------------------------------------------------
    # ISO country codes to pull. NOTE: the Adzuna API's historically
    # documented set is {at,au,be,br,ca,ch,de,es,fr,gb,id,in,it,lu,mx,nl,nz,
    # pl,sg,za} and does NOT officially include 'us'. We default to gb,us for
    # the phase-1 scope; if the live API rejects 'us', swap it for a supported
    # code (e.g. ca) or drop it.
    # NoDecode stops pydantic-settings from JSON-parsing the env string
    # (e.g. "gb,us") into list[str]; the validator below does that instead.
    countries: Annotated[list[str], NoDecode] = Field(
        default_factory=lambda: ["gb", "us"]
    )
    # Only ads created on/after this date survive cleaning.
    start_date: str = "2026-01-01"
    # The API caps results per page at 50.
    results_per_page: int = 50
    # Safety cap: never page past this point per country.
    max_pages_per_country: int = 100
    # Ads are only live for ~45 days; this mirrors the API's max_days_old.
    max_days_old: int = 45
    request_timeout_seconds: float = 30.0
    max_retries: int = 3
    backoff_base_seconds: float = 1.0
    # Be polite: one request per N seconds while looping pages.
    rate_limit_sleep_seconds: float = 1.0

    # --- Storage -------------------------------------------------------------
    data_dir: Path = Path("data")

    # --- Database (phase 1) --------------------------------------------------
    # Path to the DuckDB warehouse file. When set, the cleaned data and the
    # AI-skills analysis flags are loaded into DuckDB after the CSV load.
    db_path: Path | None = None

    # --- Google Sheets export (Looker Studio data source) --------------------
    export_to_sheets: bool = False
    # Path to a Google service-account JSON credentials file.
    google_sheets_credentials: str = ""
    # Google Sheets id (the long id in the sheet URL) or 'url'.
    google_sheets_key: str = ""
    # Print what would be exported instead of calling the Sheets API.
    sheets_dry_run: bool = False

    # --- Development / test --------------------------------------------------
    mock_mode: bool = False
    mock_rows: int = 2500
    fail_on_validation: bool = False

    # -- convenience -----------------------------------------------------------
    @property
    def has_credentials(self) -> bool:
        return bool(self.app_id and self.app_key)

    @property
    def raw_dir(self) -> Path:
        return self.data_dir / "raw"

    @property
    def processed_dir(self) -> Path:
        return self.data_dir / "processed"

    @property
    def jobs_dir(self) -> Path:
        return self.processed_dir / "jobs"

    @property
    def history_dir(self) -> Path:
        return self.processed_dir / "history"

    @property
    def analysis_dir(self) -> Path:
        return self.data_dir / "analysis"

    # -- validators ------------------------------------------------------------
    @field_validator("countries", mode="before")
    @classmethod
    def _parse_countries(cls, value: object) -> object:
        """Accept a comma-separated string ('gb,us') from the environment."""
        if isinstance(value, str):
            return [c.strip().lower() for c in value.split(",") if c.strip()]
        if isinstance(value, (list, tuple)):
            return [c.lower() for c in value]
        return value

    @field_validator("data_dir", "db_path", mode="before")
    @classmethod
    def _expand_path(cls, value: object) -> object:
        if value in (None, ""):
            return None if value is None else value
        return Path(value).expanduser() if isinstance(value, str) else value


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Return a process-wide, cached Settings instance."""
    return Settings()


__all__ = ["Settings", "get_settings"]
