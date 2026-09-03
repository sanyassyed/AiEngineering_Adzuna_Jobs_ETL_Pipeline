# adzuna-etl

An ETL pipeline that extracts job-ad data from the **Adzuna Jobs API**, cleans
and validates it, and loads it to a layered CSV store — built to scale into an
incremental **data warehouse with SCD (Type 2) dimensional modelling** and
visualisation.

## Project layout

```
adzuna-etl/
├── Makefile                     # uv-based convenience targets
├── pyproject.toml               # package metadata + deps (managed by uv)
├── .env.example                 # copy to .env and add your Adzuna credentials
├── data/                        # git-ignored data artifacts (raw + processed)
├── notebooks/
│   └── 01_eda_and_cleaning.ipynb  # generated EDA + data-quality notebook
├── scripts/
│   ├── run_etl.py                 # thin wrapper around the adzuna-etl CLI
│   └── generate_eda_notebook.py   # (re)generates the EDA notebook
├── src/adzuna_etl/
│   ├── config.py                # settings from ADZUNA_* env vars / .env
│   ├── api_client.py            # real Adzuna REST client (retries, rate limit)
│   ├── mock_client.py           # deterministic fake of the API (no key needed)
│   ├── extract.py               # paginated extraction + history normalisation
│   ├── clean.py                 # canonical, warehouse-ready schema
│   ├── validate.py              # automated data-quality checks
│   ├── load.py                  # layered CSV writer (raw + clean + masters)
│   ├── pipeline.py              # orchestration: extract -> clean -> validate -> load
│   └── cli.py                   # `adzuna-etl` console script
└── tests/                       # pytest suite
```

## Data flow

```
Adzuna API (or mock)
    │  fetch pages + history         ┌──────────────────────────────┐
    ▼                                │ data/raw/{ingest_date}/      │
EXTRACT ───────────────────────────► │  *_search.json               │ lossless raw
    │                                │  *_search_raw.csv            │
    ▼                                │  *_history.json/.csv         │
CLEAN  → normalise to CLEAN_SCHEMA   └──────────────────────────────┘
    ▼                                ┌──────────────────────────────┐
VALIDATE (dupes, nulls, salary,      │ data/processed/              │
    │      coords, date window)      │  jobs/{date}_{c}_jobs_clean.csv ■ incremental delta
    ▼                                │  adzuna_jobs_master.csv      │ ★ accumulated snapshots
LOAD   ────────────────────────────► │  adzuna_history_master.csv   │ ★ aggregated trends
                                     └──────────────────────────────┘
```

- **Raw layer** keeps the exact API payload (JSON) plus a flattened CSV, so
  nothing is lost at the source.
- **Clean layer** emits one fixed schema (`CLEAN_SCHEMA` in
  `src/adzuna_etl/schema.py`): flat columns, type-coerced salaries,
  normalised contracts, UTC datetimes, and snapshot natural key
  **`(job_id, country, ingest_date)`**.
- **Partitioned clean files** in `data/processed/jobs/` are the **incremental
  deltas** — the natural input for the future warehouse loader.

## Getting started

```bash
# 1. Install uv (if needed):   curl -LsSf https://astral.sh/uv/install.sh | sh
# 2. Create the environment and install  (project + dev extras)
uv sync

# 3a. Run against the LOCAL MOCK API — no credentials needed
uv run adzuna-etl --mock

# 3b. Run against the LIVE Adzuna API — requires a free key
cp .env.example .env      # then fill in ADZUNA_APP_ID and ADZUNA_APP_KEY
uv run adzuna-etl
```

Other targets (equivalent `uv run` commands work without `make`):

```bash
make test        #    uv run pytest
make notebook    #    uv run python scripts/generate_eda_notebook.py
make eda         #    uv run jupyter nbconvert --to notebook --execute --inplace notebooks/01_eda_and_cleaning.ipynb
```

### Options

| Flag                  | Meaning                                             |
| --------------------- | --------------------------------------------------- |
| `--mock`              | Use the deterministic local mock instead of the API |
| `--countries gb,ie`   | Comma-separated country codes to pull               |
| `--start-date 2026-01-01` | Keep only ads created on/after this date        |
| `--max-pages N`       | Cap pages fetched per country                       |
| `--data-dir path`     | Override the output root (`raw/` + `processed/`)    |
| `--fail-on-validation`| Exit non-zero if validation fails                   |
| `-v`                  | Debug logging                                       |

## About the Adzuna API (important)

- **Search endpoint** `GET https://api.adzuna.com/v1/api/jobs/{country}/search/{page}`
  returns **only currently-live ads**. Ads are typically searchable for ~45
  days (`max_days_old`), so **single backfills cannot recover job-level
  listings older than that** — e.g. jobs created in Jan–Jun 2026 are no longer
  available in the search API by the time you start pulling in late 2026.
- **History endpoint** `GET https://api.adzuna.com/v1/api/jobs/{country}/history`
  returns daily aggregate vacancy/salary statistics for hundreds of thousands
  of jobs back to ~2016 — this **does** cover the Jan 2026 → now window at the
  aggregate level and is pulled on every run.
- **Credentials**: `app_id` and `app_key` are required on every request (free
  registration at <https://developer.adzuna.com>). The pipeline runs in
  `--mock` mode without them so all engineering work is unblocked.

**Strategy for the Jan-2026 → historical window:** the pipeline is designed to
run on a schedule (e.g. daily via cron); each run adds an incremental
partition. The history endpoint fills the aggregate trend gap for Jan–Sept
2026, and the first live pull captures the snapshot of live listings from then
on. To have absolutely no job-level gap you would have had to start pulling in
Jan 2026.

## Roadmap (future phases)

1. **Warehouse load (incremental):** a `dw/` package ingesting each
   `processed/jobs/{ingest_date}_{country}_jobs_clean.csv` partition into
   DuckDB/Postgres — each run is a discrete delta, so loads are naturally
   incremental and idempotent.
2. **SCD Type 2 dimensional modelling:** `dim_company`, `dim_location`,
   `dim_category`, `dim_job`, `dim_date` with `valid_from`/`valid_to`;
   `fact_job_snapshot` keyed by `(job_id, country, ingest_date)`.
3. **Visualisation:** a BI layer (e.g. Superset / Streamlit / Metabase) over
   the warehouse / a semantic model.

## Development notes

- Managed entirely with **uv** (`uv sync`, `uv add`, `uv run`).
- The mock client seeds dirty data (string salaries, missing companies,
  inverted ranges, sloppy contract labels, duplicate ids) so cleaning and
  validation are genuinely exercised without an API key.
- Validation failures only block loading when `ADZUNA_FAIL_ON_VALIDATION=true`;
  by default the run loads and reports WARN/FAIL in the logs.

## License

MIT