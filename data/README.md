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