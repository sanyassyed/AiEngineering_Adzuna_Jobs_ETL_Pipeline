"""Command-line entrypoint (``adzuna-etl`` console script).

Examples::

    adzuna-etl --mock                              # mock API, gb+us
    adzuna-etl --mock --countries gb,us --db data/adzuna.duckdb
    adzuna-etl --mock --db data/adzuna.duckdb --export-sheets --sheets-dry-run
    adzuna-etl                                    # real API (.env), writes CSV only
    adzuna-etl --db data/adzuna.duckdb            # ...plus DuckDB load
    adzuna-etl --db data/adzuna.duckdb --export-sheets   # ...plus Google Sheets
"""

from __future__ import annotations

import argparse
import logging
from pathlib import Path

from adzuna_etl.config import Settings, get_settings
from adzuna_etl.pipeline import EtlPipeline

logger = logging.getLogger("adzuna_etl")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="adzuna-etl",
        description=(
            "Extract Adzuna job data, clean + validate it, write CSV files, load a "
            "DuckDB warehouse, and optionally push analysis views to Google Sheets."
        ),
    )
    parser.add_argument("--mock", action="store_true",
                        help="Run against a deterministic local mock of the API (no credentials needed).")
    parser.add_argument("--countries", type=str, default=None,
                        help="Comma-separated country codes, e.g. gb,us (overrides ADZUNA_COUNTRIES).")
    parser.add_argument("--start-date", type=str, default=None,
                        help="Only keep ads created on/after this date, YYYY-MM-DD (overrides ADZUNA_START_DATE).")
    parser.add_argument("--max-pages", type=int, default=None, dest="max_pages",
                        help="Cap the number of pages fetched per country.")
    parser.add_argument("--data-dir", type=Path, default=None,
                        help="Directory for raw/ and processed/ (overrides ADZUNA_DATA_DIR).")
    parser.add_argument("--db", type=Path, default=None, dest="db_path",
                        help="DuckDB file to load (overrides ADZUNA_DB_PATH).")
    parser.add_argument("--export-sheets", action="store_true", default=None,
                        help="Push the analysis views to Google Sheets (requires --db and Google creds).")
    parser.add_argument("--sheets-dry-run", action="store_true", default=None,
                        help="Print what would be exported to Google Sheets without calling the API.")
    parser.add_argument("--fail-on-validation", action="store_true", default=None,
                        help="Exit non-zero and skip loading when validation finds FAILs.")
    parser.add_argument("-v", "--verbose", action="store_true", help="Debug logging.")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s %(levelname)-7s %(name)s: %(message)s",
        datefmt="%H:%M:%S",
    )

    settings = get_settings()
    overrides: dict = {}
    if args.mock:
        overrides["mock_mode"] = True
    if args.countries is not None:
        overrides["countries"] = args.countries
    if args.start_date is not None:
        overrides["start_date"] = args.start_date
    if args.max_pages is not None:
        overrides["max_pages_per_country"] = args.max_pages
    if args.data_dir is not None:
        overrides["data_dir"] = args.data_dir
    if args.db_path is not None:
        overrides["db_path"] = args.db_path
    if args.export_sheets is not None:
        overrides["export_to_sheets"] = args.export_sheets
    if args.sheets_dry_run is not None:
        overrides["sheets_dry_run"] = args.sheets_dry_run
    if args.fail_on_validation is not None:
        overrides["fail_on_validation"] = args.fail_on_validation

    settings = Settings.model_validate({**settings.model_dump(), **overrides})

    if not settings.mock_mode and not settings.has_credentials:
        logger.error(
            "No Adzuna credentials found. Set ADZUNA_APP_ID/ADZUNA_APP_KEY in "
            ".env (see .env.example) or run with --mock."
        )
        return 2

    if settings.export_to_sheets and not settings.db_path:
        logger.error("--export-sheets needs a DuckDB warehouse: pass --db PATH or set ADZUNA_DB_PATH.")
        return 2

    try:
        result = EtlPipeline(settings).run()
    except Exception as exc:  # noqa: BLE001 - CLI should always exit cleanly
        logger.error("ETL failed: %s", exc)
        return 1

    print("\nAdzuna ETL completed successfully")
    print(f"  ingest date        : {result.ingest_date}")
    print(f"  raw ads extracted  : {result.raw_jobs_count}")
    print(f"  history rows       : {result.history_rows_count}")
    print(f"  cleaned rows       : {result.cleaned_rows_count}")
    print(f"  analysis rows      : {result.analysis_rows}")
    print(f"  validation         : {'PASSED' if result.validation.passed else 'ISSUES (logs above)'}")
    if result.db_path:
        print(f"  duckdb warehouse   : {result.db_path}")
    if result.sheets_exported is not None:
        print(f"  sheets exported    : {', '.join(result.sheets_exported)}")
    print("  files written:")
    for path in result.files_written:
        print(f"    - {path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
