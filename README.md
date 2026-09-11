# adzuna-etl

ETL + analysis pipeline for the **Adzuna Jobs API** (UK + USA): extract ->
clean -> validate -> **CSV** -> **DuckDB** -> **Google Sheets** ->
**Looker Studio**. Includes a deterministic **AI-skills demand analysis**
(technical vs non-technical roles, country-wise, over time). Built to scale
into a scheduled, incremental warehouse with SCD (Type 2) modelling.

Full requirements: see [`REQUIREMENTS.md`](REQUIREMENTS.md).

## Project layout

```
adzuna-etl/
├── Makefile, pyproject.toml, uv.lock     # uv-managed packaging
├── .env.example                          # copy to .env and add your keys
├── REQUIREMENTS.md                       # project requirements specification
├── data/                                 # git-ignored artifacts (raw/processed/analysis/duckdb)
├── notebooks/
│   ├── 01_eda_and_cleaning.ipynb         # EDA + data-quality report
│   └── 02_ai_skills_analysis.ipynb       # AI-skills demand over time
├── scripts/
│   ├── run_etl.py                        # wrapper around the `adzuna-etl` CLI
│   ├── generate_eda_notebook.py          # (re)generates notebook 01
│   └── generate_ai_analysis_notebook.py  # (re)generates notebook 02
├── src/adzuna_etl/
│   ├── config.py          # settings from ADZUNA_* env vars / .env
│   ├── api_client.py      # real Adzuna REST client (retries, rate limit)
│   ├── mock_client.py     # deterministic API fake + encoded AI ground truth
│   ├── extract.py         # paginated extraction + history normalisation
│   ├── clean.py           # canonical warehouse-ready schema
│   ├── validate.py        # data-quality checks (PASS/WARN/FAIL)
│   ├── load.py            # layered CSV writer (raw + clean + masters)
│   ├── analysis/          # AI-skills analysis package
│   │   ├── skills_taxonomy.py   # versioned AI-skill dictionary
│   │   ├── classify_roles.py    # technical / non-technical
│   │   ├── extract_skills.py    # word-boundary skill matching
│   │   ├── enrich.py            # analysis columns from clean frame
│   │   ├── aggregate.py         # weekly shares
│   │   └── trend.py             # slope + 95% CI + verdict
│   ├── warehouse.py       # DuckDB tables + views (idempotent upserts)
│   ├── sheets_export.py   # Google Sheets exporter (service account)
│   ├── pipeline.py        # orchestration incl. DB + sheets stages
│   └── cli.py             # `adzuna-etl` console script
└── tests/                 # pytest suite
```

## Data flow

```
Adzuna API (or mock)
    │  fetch pages + history      ┌───────────────────────────────┐
    ▼                             │ data/raw/{ingest_date}/       │
EXTRACT ────────────────────────► │  *_search.json                │ lossless raw
    │                             │  *_search_raw.csv             │
    ▼                             └───────────────────────────────┘
CLEAN -> CLEAN_SCHEMA (25 cols)   ┌───────────────────────────────┐
    ▼                             │ data/processed/               │
VALIDATE (dupes/nulls/salary/     │  jobs/{date}_{c}_jobs_clean.csv ■ delta
    coords/window)                │  adzuna_jobs_master.csv       │ ★ master
    ▼                             └───────────────────────────────┘
LOAD CSV -------------------------------------------┐
    ▼                                              ▼
DuckDB warehouse (fact_job_snapshot +            data/analysis/*.csv
    analysis_job_ai_flags + views)  ─────────► Google Sheets
                                                    │
                                                    ▼
                                          Looker Studio dashboards
```

- **Raw layer** keeps exact API payloads (JSON) + flattened CSV — nothing is
  lost at the source.
- **Clean layer** emits one fixed schema (`CLEAN_SCHEMA` in `schema.py`) with
  snapshot natural key `(job_id, country, ingest_date)`.
- **Analysis layer** (`data/analysis/`, DuckDB views) adds `role_class` and
  AI-skill flags WITHOUT touching the clean contract.
- **Partitioned clean files** are the incremental deltas that a phase-2
  warehouse loader will ingest.

## Getting started

```bash
uv sync                                  # 1. create .venv + install

# 2a. Mock run, UK + USA, full stack (CSV + DuckDB + sheets preview)
uv run adzuna-etl --mock --countries gb,us --db data/adzuna.duckdb \
    --export-sheets --sheets-dry-run

# 2b. Mock run with smaller data for a quick check
uv run adzuna-etl --mock --mock-rows 300 --countries gb

# 3. Live run (add your Adzuna keys to .env first)
cp .env.example .env        # fill ADZUNA_APP_ID / ADZUNA_APP_KEY
uv run adzuna-etl --db data/adzuna.duckdb

# 4. Notebooks
uv run python scripts/generate_eda_notebook.py
uv run python scripts/generate_ai_analysis_notebook.py
uv run jupyter nbconvert --to notebook --execute --inplace notebooks/02_ai_skills_analysis.ipynb
```

Other targets (equivalent `uv run` lines shown for systems without `make`):

```bash
make test        #    uv run pytest
make run-mock    #    uv run adzuna-etl --mock --data-dir data
make eda         #    (nbconvert --execute both notebooks)
```

### Options

| Flag                     | Meaning                                                          |
| ------------------------ | ---------------------------------------------------------------- |
| `--mock`                 | Use the deterministic local mock instead of the API              |
| `--countries gb,us`      | Comma-separated country codes to pull                            |
| `--start-date 2026-01-01`| Keep only ads created on/after this date                         |
| `--max-pages N`          | Cap pages fetched per country                                    |
| `--data-dir path`        | Override the output root (`raw/` + `processed/` + `analysis/`)   |
| `--db path`              | DuckDB warehouse file to upsert into                            |
| `--export-sheets`        | Push analysis views to Google Sheets (needs `--db` + creds)     |
| `--sheets-dry-run`       | Print the export instead of calling the Sheets API              |
| `--fail-on-validation`   | Exit non-zero if validation fails                                |
| `-v`                     | Debug logging                                                   |

## Google Sheets + Looker Studio setup

The pipeline exports three analysis views to one spreadsheet (one tab each):
`ai_share_latest`, `ai_share_weekly`, `ai_skill_counts`. Looker Studio then
uses the spreadsheet as a data source (Google Sheets is a native connector).

1. **Create a service account** at <https://console.cloud.google.com>:
   IAM & Admin -> Service Accounts -> + Create. Enable the **Google Sheets API**
   and **Google Drive API** for the project.
2. **Download its JSON key** to a local path, e.g. `~/.config/gcloud/sa.json`
   (never commit it).
3. **Create a Google Spreadsheet** and share it with the service account email
   (found inside the JSON, `client_email`) as **Editor**.
4. Configure:  
   ```
   ADZUNA_GOOGLE_SHEETS_CREDENTIALS=/absolute/path/to/sa.json
   ADZUNA_GOOGLE_SHEETS_KEY=your-spreadsheet-id   # long id in the sheet URL
   ADZUNA_EXPORT_TO_SHEETS=true
   ```
5. Run `uv run adzuna-etl --mock --db data/adzuna.duckdb --export-sheets`.
   First test with `--sheets-dry-run` (prints the tables, no API call).
6. In **Looker Studio**: Create -> Data source -> Google Sheets -> pick the
   spreadsheet (per-tab source works best for a chart per series).

## About the Adzuna API (important)

- **Search** `GET /v1/api/jobs/{country}/search/{page}` returns **only live
  ads** (~45 days via `max_days_old`). Job-level history before your first run
  cannot be backfilled — start pulling as early as possible.
- **History** `GET /v1/api/jobs/{country}/history` gives daily aggregate
  vacancy/salary stats back to ~2016 and covers the Jan 2026 -> now window at
  the aggregate level.
- **Country caveat:** the API's documented market set does not officially
  include `us`. Phase 1 defaults to gb,us; if the live API rejects `us`, fall
  back to a supported market (e.g. `ca`) or gb-only.
- **Credentials**: required on every request; register free at
  <https://developer.adzuna.com>. `--mock` avoids all of this for development.

## Analysis: AI-skills demand

Notebook `02_ai_skills_analysis.ipynb` + DuckDB views answer:
- share of ads mentioning AI skills, weekly, by **country** and **role class**;
- **technical vs non-technical** gap over time;
- **trend verdict** (slope in percentage-points/month, 95% CI, increasing/
  stable/decreasing) from a linear fit of the weekly shares;
- top mentioned **AI-skill terms**.

Method is deterministic and versioned (no ML): a curated taxonomy with
word-boundary regex, plus Adzuna-category/title role classification. The mock
encodes a known rising trend so tests verify the analysis recovers it.

## Roadmap (future phases)

1. **Phase 2 scheduling:** daily cron / Airflow around `uv run adzuna-etl` to
   accumulate snapshots and grow the real AI-trend series.
2. **Warehouse (incremental, SCD Type 2):** load each partition once into a
   server warehouse; dims (company, location, category, job, date) with
   valid_from/valid_to; snapshot fact keyed by `(job_id, country, ingest_date)`.
3. **BI layer:** full semantic model + dashboards (e.g. Superset / Metabase).
4. **Optional:** upgrade keyword matching to an ML classifier once enough
   labelled data exists.

## Development notes

- Managed entirely with **uv** (`uv sync`, `uv add`, `uv run`).
- The mock seeds dirty data (string salaries, missing companies, inverted
  ranges, sloppy contract labels, duplicate ids) plus an **encoded AI trend**.
- `.env` and Google service-account JSONs are git-ignored.
- Validation FAILs only block loading with `ADZUNA_FAIL_ON_VALIDATION=true`.

## License

MIT
