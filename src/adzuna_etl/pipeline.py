"""Executive pipeline: EXTRACT -> CLEAN -> VALIDATE -> LOAD (CSV + DuckDB + Sheets).

The stages are intentionally thin, individually importable modules so each
can be reused or replaced independently when the warehouse phase lands.
The pipeline now also:
  * enriches the cleaned frame with AI-skills/role-class flags,
  * upserts clean + analysis data into a DuckDB warehouse (idempotent),
  * optionally pushes the analysis views to Google Sheets for Looker Studio.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from adzuna_etl.analysis.enrich import enrich_jobs_with_ai
from adzuna_etl.api_client import AdzunaApiClient, AdzunaApiError
from adzuna_etl.clean import clean_jobs
from adzuna_etl.config import Settings, get_settings
from adzuna_etl.extract import ExtractionResult, Extractor
from adzuna_etl.load import CsvLoader, _atomic_write_df
from adzuna_etl.sheets_export import SheetsExporter, dry_run_preview
from adzuna_etl.validate import ValidationReport, validate_jobs
from adzuna_etl.warehouse import Warehouse, build_export_frames

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
    files_written: list[str] = field(default_factory=list)
    analysis_rows: int = 0
    db_path: str | None = None
    sheets_exported: list[str] | None = None


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

        if not validation.passed and self.settings.fail_on_validation:
            raise RuntimeError("Validation FAILED - data was not loaded (fail_on_validation=true)")

        loader = CsvLoader(self.settings)
        files_written = loader.save_all(extraction, clean_df)

        # ---- AI-skills analysis + database + sheets ---------------------------
        analysis_df = enrich_jobs_with_ai(clean_df)
        sheets_exported: list[str] | None = None
        db_path_str: str | None = None

        if self.settings.db_path:
            db = Warehouse(self.settings.db_path)
            try:
                db.upsert_jobs(clean_df)
                db.upsert_analysis(analysis_df)
                frames = build_export_frames(db)
            finally:
                db.close()

            db_path_str = str(self.settings.db_path)
            files_written.append(db_path_str)
            files_written.extend(self._write_analysis_artifacts(analysis_df, frames))

            if self.settings.export_to_sheets:
                if self.settings.sheets_dry_run:
                    dry_run_preview(frames)
                    sheets_exported = list(frames)
                else:
                    exporter = SheetsExporter(
                        self.settings.google_sheets_credentials,
                        self.settings.google_sheets_key,
                    )
                    sheets_exported = exporter.export_all(frames)

        return PipelineResult(
            ingest_date=extraction.ingested_at.date().isoformat(),
            raw_jobs_count=len(extraction.jobs),
            history_rows_count=len(extraction.history),
            cleaned_rows_count=len(clean_df),
            cleaning_report=cleaning_report,
            validation=validation,
            files_written=files_written,
            analysis_rows=len(analysis_df),
            db_path=db_path_str,
            sheets_exported=sheets_exported,
        )

    # -- internals ---------------------------------------------------------------
    def _write_analysis_artifacts(
        self, analysis_df: Any, frames: dict[str, Any]
    ) -> list[str]:
        """Persist the analysis flags + export views as CSVs under data/analysis/."""
        from datetime import datetime, timezone

        out_dir = self.settings.analysis_dir
        out_dir.mkdir(parents=True, exist_ok=True)
        stamp = datetime.now(timezone.utc).strftime("%Y%m%d")
        written: list[str] = []

        flags_path = out_dir / f"ai_job_flags_{stamp}.csv"
        _atomic_write_df(analysis_df, flags_path)
        written.append(str(flags_path))

        for name, frame in frames.items():
            path = out_dir / f"{name}.csv"
            _atomic_write_df(frame, path)
            written.append(str(path))
        return written

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
            status = check["status"]
            message = f"  [{status}] {check['name']}: {check['detail']}"
            if status == "PASS":
                logger.info(message)
            elif status == "WARN":
                logger.warning(message)
            else:
                logger.error(message)


__all__ = ["EtlPipeline", "PipelineResult"]
