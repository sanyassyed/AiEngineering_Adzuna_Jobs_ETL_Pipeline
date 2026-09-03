"""EXTRACT stage: pull raw data from the Adzuna API (or the mock).

Paginates the job-search endpoint per configured country, records every raw
API response (for a lossless raw layer), and normalises the history endpoint
into row-oriented data.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

from adzuna_etl.api_client import AdzunaApiClient
from adzuna_etl.config import Settings

logger = logging.getLogger(__name__)


@dataclass
class ExtractionResult:
    """Everything produced by one extraction run."""

    jobs: list[dict[str, Any]] = field(default_factory=list)
    history: list[dict[str, Any]] = field(default_factory=list)
    search_responses: dict[str, list[dict[str, Any]]] = field(default_factory=dict)
    history_responses: dict[str, dict[str, Any]] = field(default_factory=dict)
    pages_fetched: int = 0
    ingested_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


class Extractor:
    """Pulls every live ad (paginated) plus the history snapshot per country."""

    def __init__(self, client: AdzunaApiClient, settings: Settings) -> None:
        self.client = client
        self.settings = settings

    def run(self) -> ExtractionResult:
        result = ExtractionResult()
        for country in self.settings.countries:
            self._extract_country(country, result)
        logger.info(
            "Extraction complete: %d jobs, %d history rows, %d pages",
            len(result.jobs), len(result.history), result.pages_fetched,
        )
        return result

    # -- internals ---------------------------------------------------------------
    def _extract_country(self, country: str, result: ExtractionResult) -> None:
        page = 1
        total_fetched = 0
        advertised: int | None = None
        pages_for_country = 0

        while page <= self.settings.max_pages_per_country:
            response = self.client.fetch_page(
                country,
                page,
                results_per_page=self.settings.results_per_page,
                max_days_old=self.settings.max_days_old,
            )
            result.search_responses.setdefault(country, []).append(response)

            if page == 1:
                advertised = int(response.get("count") or 0)

            results = response.get("results") or []
            for ad in results:
                ad["country"] = country  # provenance for downstream layers
                result.jobs.append(ad)
            total_fetched += len(results)
            pages_for_country += 1
            result.pages_fetched += 1

            logger.info(
                "country=%s page=%d/%d returned=%d total_fetched=%d advertised=%s",
                country, page, self.settings.max_pages_per_country,
                len(results), total_fetched, advertised,
            )

            if not results:
                break  # no more pages available
            if advertised and total_fetched >= advertised:
                break  # we already have everything the API advertised
            page += 1

        logger.info("country=%s pages=%d jobs=%d", country, pages_for_country, total_fetched)

        history_response = self.client.fetch_history(country)
        result.history_responses[country] = history_response
        result.history.extend(self._normalise_history(country, history_response))

    @staticmethod
    def _normalise_history(
        country: str, payload: dict[str, Any]
    ) -> list[dict[str, Any]]:
        """Flatten the history payload into rows regardless of its exact shape.

        The API returns a ``history`` mapping of ``day -> {count: n}``; we keep
        everything and also stash the raw per-day payload for fidelity.
        """
        rows: list[dict[str, Any]] = []
        history = payload.get("history") or []
        items = history.items() if isinstance(history, dict) else history
        for day, value in items:
            if isinstance(value, dict):
                row = {
                    "country": country,
                    "day": str(day),
                    "count": value.get("count"),
                    "details_json": json.dumps(value, default=str),
                }
            else:
                row = {"country": country, "day": str(day), "count": value,
                       "details_json": None}
            rows.append(row)
        return rows


__all__ = ["Extractor", "ExtractionResult"]