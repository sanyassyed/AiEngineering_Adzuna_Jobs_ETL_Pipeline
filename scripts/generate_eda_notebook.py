"""Generate ``notebooks/01_eda_and_cleaning.ipynb`` from code cells.

Run:  uv run python scripts/generate_eda_notebook.py
Then: make eda  (executes it headlessly, saving outputs inline)
"""

from __future__ import annotations

from pathlib import Path

import nbformat as nbf

NB_PATH = Path(__file__).resolve().parent.parent / "notebooks" / "01_eda_and_cleaning.ipynb"

CELLS: list[tuple[str, str]] = [
    (
        "markdown",
        """# Adzuna jobs — EDA and data-quality report

**Pipeline:** `adzuna-etl` — Adzuna API → raw CSV → clean CSV → validation.

This notebook explores the *cleaned* layer (`data/processed/adzuna_jobs_master.csv`,
plus the aggregate history master) and documents data-quality decisions that
feed the future data-warehouse phase (incremental daily snapshots, SCD Type 2
dimensions: company, location, category; facts: job-ad snapshots by `ingest_date`).""",
    ),
    (
        "code",
        """from pathlib import Path
import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
import seaborn as sns

plt.style.use("ggplot")
pd.set_option("display.max_columns", 35)
pd.set_option("display.width", 160)

MASTER = Path("../data/processed/adzuna_jobs_master.csv").resolve()
HISTORY = Path("../data/processed/adzuna_history_master.csv").resolve()

df = pd.read_csv(
    MASTER,
    parse_dates=["created_at", "ingested_at"],
    dtype={"salary_is_predicted": bool},
)
hist = pd.read_csv(HISTORY, parse_dates=["day"])
print(f"jobs snapshot rows : {len(df):,}")
print(f"history rows       : {len(hist):,}")
print(f"ingest partition(s): {sorted(df['ingest_date'].unique())}")
df.head(3)""",
    ),
    (
        "code",
        """# Snapshot key sanity: the same job_id can appear on multiple ingest dates
key = df.groupby(["job_id", "country"]).size().reset_index(name="snapshots")
print("rows with >1 snapshot (normal for repeated daily runs):", (key["snapshots"] > 1).sum())

missing = df.isna().mean().sort_values(ascending=False)
fig, ax = plt.subplots(figsize=(10, 3))
missing.plot.bar(ax=ax)
ax.set_ylabel("null rate")
ax.set_title("Missingness per column (cleaned layer)")
plt.tight_layout()""",
    ),
    (
        "code",
        """# Categorical distributions
for col in ["category_label", "contract_time", "contract_type"]:
    if col in df:
        vc = df[col].value_counts(dropna=False).head(12)
        print(f"--- {col} ({len(vc)} unique) ---")
        print(vc.to_string(), "\\n")

print("--- top 15 companies ---")
print(df["company_name"].value_counts(dropna=False).head(15).to_string())
print("\\n--- top 15 locations ---")
print(df["location_display_name"].value_counts(dropna=False).head(15).to_string())""",
    ),
    (
        "code",
        """# Salary field health
sal = df[["salary_min", "salary_max"]].dropna()
print("salary_min  describe:")
print(sal["salary_min"].describe().round(0).to_string())
print("\\nsalary_max  describe:")
print(sal["salary_max"].describe().round(0).to_string())
print("\\ninverted pairs (min>max):", (sal["salary_min"] > sal["salary_max"]).sum())
print("salary_is_predicted true:", int(df["salary_is_predicted"].sum()))

fig, axes = plt.subplots(1, 2, figsize=(12, 4))
if not sal.empty:
    sal["salary_min"].plot.hist(ax=axes[0], bins=40)
    axes[0].set_title("salary_min histogram")
    np.log1p(sal["salary_max"]).plot.hist(ax=axes[1], bins=40)
    axes[1].set_title("salary_max (log1p) histogram")
plt.tight_layout()""",
    ),
    (
        "code",
        """# Ad creation timeline (i.e. jobs posted since the start of the window)
created = df["created_at"].dropna()
if not created.empty:
    timeline = created.dt.floor("D").value_counts().sort_index()
    fig, ax = plt.subplots(figsize=(12, 4))
    timeline.plot(ax=ax)
    ax.set_title("Ads created per day (window: from ADZUNA_START_DATE)")
    plt.tight_layout()
    print("first created:", created.min(), "| last created:", created.max())""",
    ),
    (
        "code",
        """# Salary vs category / contract (boxplots)
fig, axes = plt.subplots(1, 2, figsize=(14, 5))
if "salary_max" in df and df["salary_max"].notna().any():
    top_cats = df["category_label"].value_counts().head(8).index
    sub = df[df["category_label"].isin(top_cats) & df["salary_max"].notna()]
    sns.boxplot(data=sub, x="category_label", y="salary_max", ax=axes[0])
    axes[0].tick_params(axis="x", rotation=45)
    axes[0].set_title("salary_max by category (top 8)")
    sns.boxplot(data=df[df["salary_max"].notna()], x="contract_time", y="salary_max", ax=axes[1])
    axes[1].set_title("salary_max by contract_time")
plt.tight_layout()""",
    ),
    (
        "code",
        """# Locations on a scatter (lat/lon) + salary colouring
geo = df[df["latitude"].notna() & df["longitude"].notna() & df["salary_max"].notna()]
if len(geo):
    fig, ax = plt.subplots(figsize=(9, 7))
    sc = ax.scatter(geo["longitude"], geo["latitude"], c=geo["salary_max"],
                    cmap="viridis", s=8, alpha=0.6)
    ax.set_xlabel("longitude"); ax.set_ylabel("latitude")
    ax.set_title("Sample geolocation coloured by salary_max")
    plt.colorbar(sc, label="salary_max")
    plt.tight_layout()""",
    ),
    (
        "code",
        """# Aggregate trend from the history endpoint (covers Jan 2026 -> now)
if not hist.empty:
    daily = hist.groupby("day")["count"].sum().sort_index()
    fig, ax = plt.subplots(figsize=(12, 4))
    daily.plot(ax=ax)
    ax.set_title("Vacancy index per day (history endpoint)")
    plt.tight_layout()
    print("day range:", daily.index.min(), "->", daily.index.max())""",
    ),
    (
        "markdown",
        """## Conclusions → warehouse design

- **Snapshot model:** `(job_id, country, ingest_date)` is the natural key of one
  observation — perfect for a fact table of daily snapshots and for SCD Type 2
  on mutable attributes (salary, contract type) using `created_at`/`ingested_at`.
- **Dimensions to build later:** `dim_company` (company_name), `dim_location`
  (lat/lon + area hierarchy), `dim_category` (tag/label), `dim_job` (title),
  `dim_date` (calendar).
- **Incremental loads:** each `processed/jobs/{ingest_date}_{country}_*.csv`
  partition is a complete delta — the future loader can ingest only new partitions.
- **Known limitations:** Adzuna's search API only returns *live* listings (~45
  days), so job-level history before the pipeline starts cannot be backfilled;
  the history endpoint provides daily aggregate trends to fill that gap.

**Next phase (not in this notebook):** load masters/partitions into DuckDB or a
warehouse, build the SCD Type 2 dimensions and snapshot fact, then dashboard
with a BI tool against a semantic layer.""",
    ),
]


def build() -> nbf.NotebookNode:
    nb = nbf.v4.new_notebook()
    nb.metadata = {
        "kernelspec": {"display_name": "Python 3", "language": "python", "name": "python3"},
        "language_info": {"name": "python", "version": "3.12"},
    }
    nb.cells = [nbf.v4.new_markdown_cell(src) if kind == "markdown"
                else nbf.v4.new_code_cell(src) for kind, src in CELLS]
    return nb


def main() -> None:
    NB_PATH.parent.mkdir(parents=True, exist_ok=True)
    nbf.write(build(), NB_PATH)
    print(f"Wrote {NB_PATH}")


if __name__ == "__main__":
    main()