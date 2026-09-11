"""Generate ``notebooks/02_ai_skills_analysis.ipynb``.

Run:  uv run python scripts/generate_ai_analysis_notebook.py
Then: uv run jupyter nbconvert --to notebook --execute --inplace notebooks/02_ai_skills_analysis.ipynb
"""

from __future__ import annotations

from pathlib import Path

import nbformat as nbf

NB_PATH = Path(__file__).resolve().parent.parent / "notebooks" / "02_ai_skills_analysis.ipynb"

CELLS: list[tuple[str, str]] = [
    (
        "markdown",
        """# AI-skills demand: technical vs non-technical roles, country-wise, over time

**Question:** do job descriptions increasingly ask for AI skills, and how does
that compare between technical and non-technical roles, across countries?

**Method (all deterministic, no ML):**
1. classify each ad as technical / non-technical (Adzuna category + title keywords);
2. scan every description with a curated, versioned AI-skill dictionary
   (word-boundary regex, so words like *email* never match *AI*);
3. compute weekly AI-mention *share* (mentions / total ads) by country and role
   class - share removes ad-volume noise;
4. fit a linear trend to the weekly share and report a verdict.""",
    ),
    (
        "code",
        """from pathlib import Path
import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
import seaborn as sns

import adzuna_etl as pkg
from adzuna_etl.analysis.enrich import enrich_jobs_with_ai
from adzuna_etl.analysis.aggregate import weekly_share, latest_share
from adzuna_etl.analysis.trend import linear_trend
from adzuna_etl.analysis.extract_skills import find_ai_skills
from adzuna_etl.analysis.skills_taxonomy import TAXONOMY_VERSION

plt.style.use("ggplot")
MASTER = Path("../data/processed/adzuna_jobs_master.csv").resolve()

df = pd.read_csv(MASTER, parse_dates=["created_at", "ingested_at"])
print(f"snapshot rows: {len(df):,} | countries: {sorted(df['country'].unique())}")
print(f"ingest partition(s): {sorted(df['ingest_date'].unique())}")
print(f"taxonomy version: {TAXONOMY_VERSION} | adzuna-etl {pkg.__version__}")
an = enrich_jobs_with_ai(df)
print(f"analysis rows: {len(an):,}, AI-mentions: {int(an['ai_mentioned'].sum()):,}")
an.head(3)""",
    ),
    (
        "code",
        """# 1) Sample flagged descriptions (sanity check of the matcher)
flagged = an[an["ai_mentioned"]]
print(f"ads mentioning AI skills: {len(flagged):,} / {len(an):,} = {len(flagged)/len(an):.1%}")
for _, row in flagged.sample(min(5, len(flagged)), random_state=1).iterrows():
    print(f"\n[{row['country']}] {row['role_class']} | {row['title']}")
    print("  ", row["description"][:180])""",
    ),
    (
        "code",
        """# 2) Weekly AI-mention share by country and role class
weekly = weekly_share(an)
fig, ax = plt.subplots(figsize=(12, 5))
for (country, rc), grp in weekly.groupby(["country", "role_class"]):
    grp = grp.sort_values("week")
    ax.plot(grp["week"], grp["ai_share"], marker="o", ms=3, label=f"{country} - {rc}")
ax.legend(title="country - role class", fontsize=8)
ax.set_ylabel("share of ads mentioning AI skills")
ax.set_ylim(0, None)
plt.xticks(rotation=90)
plt.title("Weekly AI-skill mention share")
plt.tight_layout()
weekly.tail(8)""",
    ),
    (
        "code",
        """# 3) Trend table: slope (percentage points / month) + 95% CI + verdict
trend = linear_trend(weekly)
print(trend.to_string(index=False))
print("
verdict summary:", trend["verdict"].value_counts().to_dict())""",
    ),
    (
        "code",
        """# 4) Latest-week country comparison
latest = latest_share(an)
fig, ax = plt.subplots(figsize=(9, 4))
sns.barplot(data=latest, x="country", y="ai_share", hue="role_class", ax=ax)
ax.set_ylabel("AI-mention share (latest week)")
plt.title("Latest-week AI-skill demand by country and role class")
plt.tight_layout()
latest.sort_values("ai_share", ascending=False)""",
    ),
    (
        "code",
        """# 5) Which AI skills are mentioned most? (term level, from flagged ads)
from collections import Counter
term_counts = Counter()
for desc in an.loc[an["ai_mentioned"], "description"]:
    for term, n in find_ai_skills(desc).terms.items():
        term_counts[term] += n
fig, ax = plt.subplots(figsize=(9, 6))
pd.Series(term_counts).sort_values().tail(15).plot.barh(ax=ax, color="steelblue")
ax.set_xlabel("mentions")
plt.title("Top AI-skill terms mentioned in descriptions")
plt.tight_layout()""",
    ),
    (
        "code",
        """# 6) Technical minus non-technical gap over time
piv = weekly.pivot_table(index="week", columns=["country", "role_class"], values="ai_share")
gap = piv["technical"] - piv["non-technical"]
gap.plot(figsize=(11, 4), marker="o", ms=3)
plt.axhline(0, color="grey", lw=1)
plt.xticks(rotation=90)
plt.ylabel("gap in AI-mention share")
plt.title("Technical minus non-technical AI-mention share")
plt.tight_layout()""",
    ),
    (
        "markdown",
        """## Conclusion & automation path

- **Direction:** the weekly share series + trend table (slope in
  percentage-points/month with 95% CIs) answer "is it increasing?" directly.
- **Limitations:** the search API only exposes live ads (~45 days), so this
  trend builds up as the pipeline runs; the history endpoint fills aggregate
gaps; keyword matching is a curated approximation, not a hire decision.
- **Operational:** run ``adzuna-etl --db data/adzuna.duckdb --export-sheets``
  and the same views land in Google Sheets for Looker Studio dashboards.""",
    ),
]


def build() -> nbf.NotebookNode:
    nb = nbf.v4.new_notebook()
    nb.metadata = {
        "kernelspec": {"display_name": "Python 3", "language": "python", "name": "python3"},
        "language_info": {"name": "python", "version": "3.12"},
    }
    nb.cells = [
        nbf.v4.new_markdown_cell(src) if kind == "markdown" else nbf.v4.new_code_cell(src)
        for kind, src in CELLS
    ]
    return nb


def main() -> None:
    NB_PATH.parent.mkdir(parents=True, exist_ok=True)
    nbf.write(build(), NB_PATH)
    print(f"Wrote {NB_PATH}")


if __name__ == "__main__":
    main()

