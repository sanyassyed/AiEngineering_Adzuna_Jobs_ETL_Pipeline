"""Runtime configuration, loaded from environment variables / ``.env``.

All settings are prefixed with ``ADZUNA_`` (e.g. ``ADZUNA_APP_ID``).
Fields map 1:1 to the ``.env.example`` file committed in the repo root.
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


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
    # ISO 3166-1 alpha-2 country codes supported by the Adzuna API.
    countries: list[str] = ["gb"]
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

    # -- validators ------------------------------------------------------------
    @field_validator("countries", mode="before")
    @classmethod
    def _parse_countries(cls, value: object) -> object:
        """Accept a comma-separated string ('gb,ie') from the environment."""
        if isinstance(value, str):
            return [c.strip().lower() for c in value.split(",") if c.strip()]
        if isinstance(value, (list, tuple)):
            return [c.lower() for c in value]
        return value

    @field_validator("data_dir", mode="before")
    @classmethod
    def _expand_data_dir(cls, value: object) -> object:
        return Path(value).expanduser() if isinstance(value, str) else value


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Return a process-wide, cached Settings instance."""
    return Settings()


__all__ = ["Settings", "get_settings"]