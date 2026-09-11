# Data directory

This directory is **git-ignored**; it holds data artifacts produced by the pipeline.

| Path                          | Layer    | Content                                                     |
| ----------------------------- | -------- | ------------------------------------------------------------ |
| `raw/{ingest_date}/`          | Raw      | Lossless API payloads (JSON) + one flat CSV per country.     |
| `processed/jobs/`             | Clean    | One cleaned CSV per `{ingest_date}_{country}` (incremental delta). |
| `processed/history/`          | Clean    | Normalised Adzuna historical daily aggregates (trend data).  |
| `processed/adzuna_jobs_master.csv`    | Clean    | Accumulated snapshot of every cleaned run (dedup key: job_id + country + ingest_date). |
| `processed/adzuna_history_master.csv` | Clean    | Accumulated daily-aggregate history.                        |

The cleaned partitions are the natural **incremental boundaries** for the future
data-warehouse loader: each file is the delta produced by one pipeline run.
| Path                          | Layer    | Content                                                     |
| ----------------------------- | -------- | ------------------------------------------------------------ |
| `analysis/ai_job_flags_*.csv` | Analysis | Per-snapshot role_class + AI-skill mention flags.            |
| `analysis/ai_share_weekly.csv`| Analysis | Weekly AI-mention share by country x role class.            |
| `analysis/ai_share_latest.csv`| Analysis | Latest-week share (country x role class).                   |
| `analysis/ai_skill_counts.csv`| Analysis | Per-group AI-skill mention totals by country x role class.  |
| `adzuna.duckdb`               | Warehouse| DuckDB with fact_job_snapshot + analysis_job_ai_flags + views.| 

These analysis outputs are exactly what `adzuna-etl --export-sheets` pushes to
Google Sheets for Looker Studio.
