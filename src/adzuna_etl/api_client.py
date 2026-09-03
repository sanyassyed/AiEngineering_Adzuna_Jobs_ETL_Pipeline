"""Resilient HTTP client for the Adzuna Jobs API.

Adzuna REST base:  https://api.adzuna.com/v1/api

  Search : GET /v1/api/jobs/{country}/search/{page}
           ?app_id=...&app_key=...&results_per_page=50&max_days_old=45
  History: GET /v1/api/jobs/{country}/history

The job-search endpoint only exposes *currently live* ads, and the history
endpoint exposes aggregate daily vacancy / salary stats. See the README for
what that means for backfilling.
"""

from __future__ import annotations

import logging
import time
from typing import Any

import requests

logger = logging.getLogger(__name__)

API_ROOT = "https://api.adzuna.com/v1/api"
RETRYABLE_STATUS = {429, 500, 502, 503, 504}


class AdzunaApiError(RuntimeError):
    """Raised when the Adzuna API returns a non-recoverable error."""


class AdzunaApiClient:
    """Authenticated, retrying, rate-limited client for the Adzuna API."""

    def __init__(
        self,
        app_id: str,
        app_key: str,
        *,
        timeout: float = 30.0,
        max_retries: int = 3,
        backoff_base: float = 1.0,
        rate_limit_sleep: float = 0.0,
    ) -> None:
        if not app_id or not app_key:
            raise AdzunaApiError(
                "Adzuna credentials are missing. Set ADZUNA_APP_ID and "
                "ADZUNA_APP_KEY (copy .env.example to .env) or use --mock."
            )
        self.app_id = app_id
        self.app_key = app_key
        self.timeout = timeout
        self.max_retries = max_retries
        self.backoff_base = backoff_base
        self.rate_limit_sleep = rate_limit_sleep
        self._session = requests.Session()

    # -- context manager ------------------------------------------------------
    def close(self) -> None:
        self._session.close()

    def __enter__(self) -> "AdzunaApiClient":
        return self

    def __exit__(self, *exc_info: Any) -> None:
        self.close()

    # -- public API ------------------------------------------------------------
    def fetch_page(
        self,
        country: str,
        page: int,
        *,
        results_per_page: int = 50,
        max_days_old: int = 45,
    ) -> dict[str, Any]:
        """Fetch one 1-based page of live job ads for ``country``."""
        url = f"{API_ROOT}/jobs/{country}/search/{page}"
        params: dict[str, Any] = {
            "app_id": self.app_id,
            "app_key": self.app_key,
            "results_per_page": results_per_page,
            "content-type": "application/json",
        }
        if max_days_old:
            params["max_days_old"] = max_days_old
        return self._get(url, params)

    def fetch_history(self, country: str) -> dict[str, Any]:
        """Fetch the aggregate daily vacancy/salary history for ``country``."""
        url = f"{API_ROOT}/jobs/{country}/history"
        params: dict[str, Any] = {
            "app_id": self.app_id,
            "app_key": self.app_key,
            "content-type": "application/json",
        }
        return self._get(url, params)

    # -- internals --------------------------------------------------------------
    def _get(self, url: str, params: dict[str, Any]) -> dict[str, Any]:
        last_error: Exception | None = None
        for attempt in range(self.max_retries + 1):
            if attempt:
                delay = self.backoff_base * (2 ** (attempt - 1))
                logger.warning(
                    "Transient failure, retrying %s in %.1fs (attempt %d/%d)",
                    url, delay, attempt, self.max_retries,
                )
                time.sleep(delay)
            if self.rate_limit_sleep:
                time.sleep(self.rate_limit_sleep)
            try:
                response = self._session.get(url, params=params, timeout=self.timeout)
            except requests.RequestException as exc:  # network-level failure
                last_error = exc
                continue
            if response.status_code == 200:
                return response.json()
            if response.status_code in RETRYABLE_STATUS and attempt < self.max_retries:
                continue
            raise AdzunaApiError(
                f"Adzuna API HTTP {response.status_code} for {url}: "
                f"{response.text[:300]}"
            )
        raise AdzunaApiError(f"Adzuna API request failed for {url}: {last_error}")


__all__ = ["AdzunaApiClient", "AdzunaApiError", "API_ROOT"]