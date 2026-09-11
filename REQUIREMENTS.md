# Project Requirements — `adzuna-etl`

| Field            | Value                                                             |
| ---------------- | ----------------------------------------------------------------- |
| Document type    | Software requirements specification (phase 1)                     |
| Status           | Approved — phase 1 built and validated on mock + storage layers   |
| Date             | 2026-09-11                                                        |
| Owner            | Data engineering team                                             |
| Related docs     | `README.md`, `src/adzuna_etl/schema.py` (data contract), `01_eda_and_cleaning.ipynb`, `02_ai_skills_analysis.ipynb` |

Requirement IDs are stable and traceable to implementation (§15). New
requirements must be added with a new ID, never by renumbering.

---

## 1. Purpose

**adzuna-etl** is an ETL + analysis pipeline that:

1. **Extracts** job-ad data from the Adzuna Jobs API for the **UK (gb)** and
   **USA (us)** markets over the window **Jan 2026 -> present**;
2. **Stores** a lossless raw layer and a cleaned layer as **CSV**, then loads
   the cleaned + analysis data into a local **DuckDB** database;
3. **Analyses** job descriptions for **AI-skill demand**: technical vs
   non-technical roles, country-wise, and over time (is it increasing?);
4. **Pushes** analysis results to **Google Sheets**, consumed by
   **Google Looker Studio** dashboards;
5. Is structured for a **phase-2** evolution into a scheduled, incremental
   warehouse with SCD (Type 2) dimensional modelling.

## 2. Goals and objectives

| ID  | Goal                                                                                         |
| --- | -------------------------------------------------------------------------------------------- |
| G01 | Pull Adzuna job data for the window Jan 2026 -> current, for gb and us.                       |
| G02 | Persist raw + cleaned data as CSV in a layered layout (raw -> processed).                     |
| G03 | Store cleaned + analysis data in a queryable database (DuckDB) within phase 1.                |
| G04 | Quantify AI-skill demand signals in job descriptions; split by technical / non-technical roles and by country. |
| G05 | Determine whether AI-skill demand is increasing over the available window (trend + CI).       |
| G06 | Deliver the analysis to Google Sheets + Looker Studio for dashboards.                         |
| G07 | Use a packageable, uv-managed structure that scales into a scheduled incremental warehouse.   |

## 3. Scope

**In scope (phase 1):** authenticated extraction (search + history) for gb/us,
lossless raw layer, canonical cleaning, automated validation, CSV loading,
DuckDB loading, AI-skills role + text analysis, Google Sheets export (incl.
dry-run), Looker Studio consumption, EDA notebooks, unit tests, packaging,
documentation.

**Out of scope (phase 2+):** periodic scheduling/orchestration of runs, full
incremental warehouse (SCD Type 2 dimensions + snapshot fact in a server DB),
advanced/ML-based NLP. Requirements for these are captured in advance in §14.

## 4. Stakeholders

- **Data engineers** — build, run, maintain, and schedule the pipeline.
- **Analysts / BI consumers** — EDA notebooks and Looker Studio dashboards.
- **Platform/DevOps** — phase-2 scheduling and warehouse hosting.
- **Hiring / product teams (consumer of insights)** — AI-skills demand views.

## 5. Functional requirements

| ID    | Requirement                                                                                                |
| ----- | ---------------------------------------------------------------------------------------------------------- |
| FR-01 | Configuration via environment / `.env` with the `ADZUNA_` prefix; credentials are `ADZUNA_APP_ID` / `ADZUNA_APP_KEY`; comma-separated `ADZUNA_COUNTRIES` is accepted. |
| FR-02 | Extract live listings from the search endpoint per country, paginated (default 50/page, page cap, `max_days_old`). Default markets: gb, us. |
| FR-03 | Extract the daily aggregate history endpoint per country on every run.                                     |
| FR-04 | Persist a lossless raw layer: original API JSON payloads + flattened raw CSV, partitioned by ingest date.   |
| FR-05 | Clean and normalise ads into the fixed `CLEAN_SCHEMA` (25 columns): flattened nested objects, coerced types, UTC timestamps. |
| FR-06 | De-duplicate on the snapshot natural key `(job_id, country, ingest_date)`, keep first.                     |
| FR-07 | Enforce the date window: keep ads `created_at >= start_date` (default `2026-01-01`).                        |
| FR-08 | Run data-quality checks with PASS/WARN/FAIL surfaced in logs; optionally hard-block on FAIL.                |
| FR-09 | Load cleaned data as per-day, per-country partition CSVs and accumulated masters, with atomic writes.       |
| FR-10 | Deterministic mock API client (same interface as live client) that also encodes a rising AI-mention ground truth for tests. |
| FR-11 | `adzuna-etl` CLI with flags `--mock`, `--countries`, `--start-date`, `--max-pages`, `--data-dir`, `--db`, `--export-sheets`, `--sheets-dry-run`, `--fail-on-validation`, `-v`. |
| FR-12 | Generated, headlessly executable EDA notebook (`01_eda_and_cleaning.ipynb`).                               |
| FR-13 | Unit tests for cleaning rules, schema contract, config parsing, analysis, warehouse, sheets export, and end-to-end mock pipeline. |
| FR-14 | Every run is idempotent and incremental-safe: one partition per (ingest_date, country); re-runs replace, never duplicate. |
| FR-15 | Deterministic, versioned role classification (technical / non-technical) from Adzuna category + title keywords. |
| FR-16 | Versioned AI-skill taxonomy dictionary applied to descriptions with word-boundary matching.                |
| FR-17 | Ad-level analysis flags: `role_class`, `ai_mentioned`, per-group mention counts, taxonomy + classifier versions. |
| FR-18 | Weekly AI-mention share KPIs by (week, country, role_class) and per-group skill counts.                     |
| FR-19 | Trend estimation: slope (percentage points/month), 95% CI, p-value, verdict (increasing / stable / decreasing). |
| FR-20 | DuckDB warehouse: `fact_job_snapshot` + `analysis_job_ai_flags` tables (keyed by the snapshot natural key) and export views; idempotent INSERT OR REPLACE loads. |
| FR-21 | Google Sheets export of the analysis views via a service account; `--sheets-dry-run` prints instead of calling the API. |
| FR-22 | Looker Studio can consume the exported Google Sheets as a data source (documented setup).                 |
| FR-23 | Generated, headlessly executable AI-skills analysis notebook (`02_ai_skills_analysis.ipynb`).               |
| FR-24 | Tests verify that the analysis layer recovers the mock-encoded rising AI-mention trend.                    |

## 6. Non-functional requirements

| ID     | Category      | Requirement                                                                                          |
| ------ | ------------- | ---------------------------------------------------------------------------------------------------- |
| NFR-01 | Performance   | Page fetches rate-limited (default 1 req/s) with timeouts; bounded partition files; DuckDB queries return in seconds. |
| NFR-02 | Reliability   | Retries with exponential backoff on transient API failures; atomic file writes; idempotent DB upserts. |
| NFR-03 | Security      | Credentials only in `.env` (git-ignored), never logged; live mode guards missing credentials; Sheets service-account JSON never committed. |
| NFR-04 | Maintainability | `src/` layout, modular stages, one canonical schema, versioned analysis artifacts.                   |
| NFR-05 | Reproducibility | `uv.lock` pins dependencies; mock is seeded; taxonomy/classifier versions stamped in outputs.         |
| NFR-06 | Usability      | CLI help, README, Makefile/uv targets, clear error messages.                                          |
| NFR-07 | Scalability    | Partitioned CSVs + DuckDB views map 1:1 to phase-2 incremental loads; no global state.                |
| NFR-08 | Portability    | Python >= 3.10, uv-managed; CSV + DuckDB + Google Sheets cover the phase-1 stack.                    |
| NFR-09 | Observability  | Step logging with counts, validation report, CLI summary, and analysis artifacts under `data/analysis/`. |

## 7. Data requirements and quality rules

| ID    | Data rule                                                                                                      |
| ----- | -------------------------------------------------------------------------------------------------------------- |
| DR-01 | The cleaned dataset has exactly the columns of `CLEAN_SCHEMA`, in order.                                       |
| DR-02 | `created_at` / `ingested_at` are UTC and tz-aware; `ingest_date` is the YYYY-MM-DD snapshot partition.           |
| DR-03 | Salaries are floats; inverted pairs are swapped; a missing half is filled from the other; currency defaults per country. |
| DR-04 | Coordinates within bounds (`abs(lat) <= 90`, `abs(lon) <= 180`).                                                 |
| DR-05 | The raw layer preserves full API fidelity; cleaning is never the only copy of source data.                      |
| DR-06 | Duplicate definition is the exact snapshot key `(job_id, country, ingest_date)`; cross-country same-id rows are distinct snapshots. |
| DR-07 | A FAIL validation check flags the batch as not warehouse-ready; WARN/FAIL are always reported.                   |
| DR-08 | Text preprocessing for analysis (lowercase, unicode normalisation, HTML/control-char stripping, whitespace collapsing) is applied only in the analysis layer; raw/clean text stays untouched. |
| DR-09 | Bare acronyms `AI`/`ML` match on word boundaries only; phrase matching is case-insensitive and longest-first.    |

## 8. API contract notes (Adzuna)

- Base URL: `https://api.adzuna.com/v1/api`
- Search: `GET /jobs/{country}/search/{page}` with `app_id`, `app_key`,
  `results_per_page` (<= 50), `max_days_old`, `content-type=application/json`;
  response exposes `count` and `results`.
- History: `GET /jobs/{country}/history` — daily aggregate count/salary stats.
- Ads stay live ~45 days (`max_days_old`), then disappear from search.
- Credentials are mandatory on every call; the API is an external contract that
  can change, so the client retries transient failures and reports clear errors.
- **Country caveat:** the documented API market set historically is
  {at,au,be,br,ca,ch,de,es,fr,gb,id,in,it,lu,mx,nl,nz,pl,sg,za} and does not
  officially include `us`. Phase 1 defaults to gb,us; the live run must verify
  `us` is accepted and fall back to a supported market (e.g. ca) or gb-only if not.

## 9. Analysis methodology (AI-skills demand)

### 9.1 Questions
1. What share of adverts ask for AI skills, now and over time?
2. Technical vs non-technical roles: how do the shares differ?
3. Country-wise (gb vs us): how do the shares differ?
4. Is the share increasing? By how much, and is the change statistically credible?

### 9.2 Role classification (deterministic)
- Primary signal: Adzuna category. Technical set = {`it-jobs`, `engineering-jobs`}.
- Secondary signal: high-signal title keywords (engineer, developer, programmer,
  software, devops, scientist, analyst, data, ml, ai, platform, cloud, python,
  sql, java, ... ) rescue ads with a missing/ambiguous category.
- Everything else is non-technical. Mapping is versioned (`role_classifier_version`).

### 9.3 AI-skill taxonomy (deterministic dictionary, versioned)
| Group | Example terms                                        |
| ----- | ---------------------------------------------------- |
| general_ai | artificial intelligence, AI, ML, data science, automation, ai-powered |
| machine_learning | machine learning, deep learning, neural network, NLP, computer vision, reinforcement learning, forecasting |
| ml_tools | TensorFlow, PyTorch, scikit-learn, Keras, XGBoost, Hugging Face |
| generative_ai | LLM(s), generative AI, ChatGPT, Claude, Gemini, Copilot, LangChain, RAG, vector database, prompt engineering |

Matching: case-insensitive word-boundary regex; longest phrases match first;
`AI`/`ML` never match inside words (email, aim, available).

### 9.4 Metrics and how we answer "is it increasing?"
1. **Point-in-time share**: ads mentioning any AI skill / total ads, by country
   and role class.
2. **Weekly share series** (mentions / total ads per week) - the denominator
   removes ad-volume noise.
3. **Trend**: OLS over the weekly shares; slope (percentage points/month),
   95% CI, two-sided p-value, and verdict: increasing / stable / decreasing.
4. **Country + role comparison**: latest-week shares and window averages.
5. **Skill composition**: top mentioned terms by country.

### 9.5 Caveats (documented in the notebook too)
- Search API = live ads only (~45 days) -> description-level history before the
  first run cannot be backfilled; the trend builds forward. The history endpoint
  fills the aggregate gap for Jan 2026 -> now.
- We measure adverts, not hires (demand proxy).
- Keyword matching is a curated approximation; sample-flag review is part of the
  analysis notebook.
- Ad-volume mix changes are controlled by reporting shares within role class.

## 10. Data cleaning design

Cleaning happens in two layers:

**Structural (canonical schema, `clean.py`):** flatten nested API objects
(company, location, category), coerce salary/coordinate types, swap inverted
salary pairs and fill missing halves, set per-country currency defaults,
normalise contract labels (Full_Time -> full_time), parse UTC datetimes,
drop rows without an id, de-duplicate on the snapshot key, filter to the date
window, enforce column order/types, and run the QA battery (dupes, nulls,
salary order, coordinates, date window).

**Text (analysis layer only, never touching raw/clean stores):** lowercase,
Unicode normalisation, HTML/control-char stripping, &nbsp; handling,
whitespace collapsing, then word-boundary skill matching against the
versioned taxonomy (`DR-08`, `DR-09`).

## 11. Execution plan (how we run the project)

| Step | Command (uv)                                                | Produces                                          |
| ---- | ----------------------------------------------------------- | ------------------------------------------------- |
| Dev loop | `uv run adzuna-etl --mock --countries gb,us`            | data/raw/*, data/processed/*                      |
| + DB      | `... --db data/adzuna.duckdb`                             | DuckDB warehouse + data/analysis/*               |
| + Sheets  | `... --export-sheets --sheets-dry-run`                    | printed preview (or real Sheets with creds)      |
| Live      | `uv run adzuna-etl --db data/adzuna.duckdb`             | real Adzuna data (needs .env creds + api reachability of `us`) |
| Analyse   | `uv run python scripts/generate_eda_notebook.py & 02...` + nbconvert | notebooks 01/02 with charts          |
| Test      | `uv run pytest`                                            | unit test report                                 |

Phase 2 will wrap the same entrypoint in a scheduler (cron / Airflow) so a
snapshot is recorded every day and the weekly AI-trend series grows.

## 12. Constraints and assumptions

| ID    | Statement                                                                                          |
| ----- | --------------------------------------------------------------------------------------------------- |
| AS-01 | Adzuna requires registration; `app_id`/`app_key` are mandatory on every API call.                   |
| AS-02 | The search API only exposes live ads (~45 days); job-level descriptions from Jan-Sep 2026 are not
         retrievable retroactively.                                                                   |
| AS-03 | The Jan-2026 -> now window is realised as: history aggregates (Jan onwards) + accumulated snapshots
         from the first live run onward.                                                              |
| AS-04 | The `us` market may not exist on the Adzuna API; fall back to a supported code or gb-only if rejected. |
| AS-05 | Development runs use the seeded mock (no API cost / no keys); real data lands once live mode is run. |
| AS-06 | Google Sheets export needs a service-account JSON (user-created); until then `--sheets-dry-run` covers the workflow. |
| AS-07 | Phase 1 storage = CSV + DuckDB; a server warehouse (Postgres/etc.) is phase 2.                     |
| AS-08 | Usage complies with the Adzuna API terms of service.                                                |

## 13. Acceptance criteria (definition of done)

| ID  | Criterion                                                                                          |
| --- | --------------------------------------------------------------------------------------------------- |
| AC-01 | `uv run pytest` passes (all tests green).                                                           |
| AC-02 | `uv run adzuna-etl --mock --countries gb,us --db data/adzuna.duckdb` completes end-to-end: CSVs, DuckDB tables (fact + analysis), and `data/analysis/*` written; validation PASSED. |
| AC-03 | Cleaned CSV matches `CLEAN_SCHEMA` column-for-column.                                               |
| AC-04 | Notebooks 01 and 02 execute headlessly with zero errors.                                            |
| AC-05 | The analysis recovers the mock's encoded rising AI-mention trend (unit-tested).                     |
| AC-06 | `--export-sheets --sheets-dry-run` prints the export views without calling Google.                  |
| AC-07 | Live mode fails gracefully with an actionable message when credentials are absent.                  |
| AC-08 | README documents setup (API key, Google service account, Looker Studio connection).                 |

## 14. Requirements for later phases (not in phase-1 scope)

| ID      | Requirement                                                                                         |
| ------- | --------------------------------------------------------------------------------------------------- |
| R-SCH-01| Periodic scheduling (daily cron / Airflow) wrapping the existing entrypoint to accumulate snapshots. |
| R-DW-01 | Incremental, idempotent load of each `processed/jobs/{ingest_date}_{country}_*.csv` partition into a server warehouse. |
| R-DW-02 | SCD Type 2 dimensions (company, location, category, job, date) with valid_from/valid_to and current flags. |
| R-DW-03 | Snapshot fact table keyed by `(job_id, country, ingest_date)`.                                       |
| R-DW-04 | BI layer (e.g. Apache Superset / Metabase / Streamlit) over the warehouse/semantic model.           |
| R-NLP-01 | Optional upgrade of rule-based skill matching to an ML classifier once enough labelled data exists.  |

## 15. Traceability (requirement -> implementation)

| Requirements          | Modules                                                                                               |
| --------------------- | ----------------------------------------------------------------------------------------------------- |
| FR-01, FR-11          | `config.py`, `cli.py`                                                                                 |
| FR-02 .. FR-04        | `api_client.py`, `extract.py`, `load.py` (raw layer)                                                  |
| FR-05 .. FR-07        | `clean.py`, `schema.py`                                                                               |
| FR-08                | `validate.py`                                                                                         |
| FR-09, FR-14          | `load.py` (partitions + masters, atomic writes)                                                       |
| FR-10                | `mock_client.py` (incl. encoded AI ground truth)                                                      |
| FR-12, FR-23          | `scripts/generate_eda_notebook.py`, `scripts/generate_ai_analysis_notebook.py`                        |
| FR-15                | `analysis/classify_roles.py`                                                                          |
| FR-16, FR-17          | `analysis/skills_taxonomy.py`, `analysis/extract_skills.py`, `analysis/enrich.py`                     |
| FR-18                | `analysis/aggregate.py`                                                                               |
| FR-19                | `analysis/trend.py`                                                                                   |
| FR-20                | `warehouse.py` (tables, views, upserts)                                                               |
| FR-21, FR-22          | `sheets_export.py`; README "Google Sheets setup"                                                    |
| FR-13, FR-24          | `tests/test_analysis.py`, `test_warehouse.py`, `test_sheets_export.py`, `test_pipeline.py`            |
| FR-06, DR-08, DR-09    | `clean.py`, `analysis/extract_skills.py`                                                              |

## 16. Change log

| Version | Date       | Change                                                                                                |
| ------- | ---------- | ----------------------------------------------------------------------------------------------------- |
| v0.1    | 2026-09-03 | Phase-1 baseline (extract -> clean -> validate -> CSV), EDA notebook.                                  |
| v0.2    | 2026-09-11 | AI-skills analysis (FR-15..24), DuckDB warehouse (FR-20), Google Sheets + Looker Studio (FR-21..22), gb/us default markets, phase-2 scheduling deferred. |
