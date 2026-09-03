"""Executive pipeline: EXTRACT -> CLEAN -> VALIDATE -> LOAD.

The stages are intentionally thin, individually importable modules so each
can be reused or replaced independently when the data-warehouse phase lands
(e.g. swap the CSV loader for a SQL loader without touching clean/validate).
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any

from adzuna_etl.api_client import AdzunaApiClient, AdzunaApiError
from adzuna_etl.clean import clean_jobs
from adzuna_etl.config import Settings, get_settings
from adzuna_etl.extract import ExtractionResult, Extractor
from adzuna_etl.load import CsvLoader
from adzuna_etl.validate import ValidationReport, validate_jobs

logger = logging.getLogger(__name__)


@dataclass
class PipelineResult:
    """Summary of one pipeline run."""

    ingest_date: str
    raw_jobs_count: int
    history_rows_count: int
    cleaned_rows_count: int
    cleaning_report: dict[str, int]
    validation: ValidationReport
    files_written: list[str]


class EtlPipeline:
    """Run the full extract -> clean -> validate -> load flow."""

    def __init__(self, settings: Settings | None = None) -> None:
        self.settings = settings or get_settings()

    def run(self) -> PipelineResult:
        if self.settings.mock_mode:
            logger.warning("MOCK MODE: generating local sample data instead of calling the Adzuna API.")
        client = self._build_client()
        with client:
            extractor = Extractor(client, self.settings)
            extraction: ExtractionResult = extractor.run()

        clean_df, cleaning_report = clean_jobs(
            extraction.jobs, self.settings, extraction.ingested_at
        )
        validation = validate_jobs(clean_df, self.settings)
        self._log_validation(validation)

        loader = CsvLoader(self.settings)
        files_written = loader.save_all(extraction, clean_df)

        if not validation.passed and self.settings.fail_on_validation:
            raise RuntimeError("Validation FAILED - data was not loaded (fail_on_validation=true)")

        return PipelineResult(
            ingest_date=extraction.ingested_at.date().isoformat(),
            raw_jobs_count=len(extraction.jobs),
            history_rows_count=len(extraction.history),
            cleaned_rows_count=len(clean_df),
            cleaning_report=cleaning_report,
            validation=validation,
            files_written=files_written,
        )

    # -- internals ---------------------------------------------------------------
    def _build_client(self) -> AdzunaApiClient:
        settings = self.settings
        if settings.mock_mode:
            from adzuna_etl.mock_client import MockAdzunaClient

            return MockAdzunaClient(
                start_date=settings.start_date,
                rows_per_country=settings.mock_rows,
                countries=tuple(settings.countries),
            )
        return AdzunaApiClient(
            settings.app_id,
            settings.app_key,
            timeout=settings.request_timeout_seconds,
            max_retries=settings.max_retries,
            backoff_base=settings.backoff_base_seconds,
            rate_limit_sleep=settings.rate_limit_sleep_seconds,
        )

    @staticmethod
    def _log_validation(report: ValidationReport) -> None:
        for check in report.checks:
            if check["status"] == "PASS":
                logger.info("  [PASS] %s: %s", check["name"], check["detail"])
            elif check["status"] == "WARN":
                logger.warning("  [WARN] %s: %s", check["name"], check["detail"])
            else:
                logger.error("  [FAIL] %s: %s", check["name"], check["detail"])


__all__ = ["EtlPipeline", "PipelineResult"]