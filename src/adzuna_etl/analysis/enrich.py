"""Attach AI-analysis fields to a cleaned jobs frame.

Pure function over the canonical clean schema: adds ``role_class`` and the
AI-skill mention flags without mutating the clean CSV contract. The result is
what gets stored in the DuckDB ``analysis_job_ai_flags`` table and written to
``data/analysis/`` on every database-enabled run.
"""

from __future__ import annotations

from datetime import datetime, timezone

import pandas as pd

from adzuna_etl.analysis.classify_roles import ROLE_CLASSIFIER_VERSION, add_role_class
from adzuna_etl.analysis.extract_skills import find_ai_skills
from adzuna_etl.analysis.skills_taxonomy import BY_GROUP_COLUMN_MAP, TAXONOMY_VERSION

ANALYSIS_COLUMNS: list[str] = [
    "job_id",
    "country",
    "ingest_date",
    "created_at",
    "title",
    "description",
    "category_tag",
    "category_label",
    "role_class",
    "ai_mentioned",
    "ai_total_mentions",
    "ai_general_ai",
    "ai_machine_learning",
    "ai_ml_tools",
    "ai_generative_ai",
    "taxonomy_version",
    "role_classifier_version",
]


def enrich_jobs_with_ai(df: pd.DataFrame) -> pd.DataFrame:
    """Return the analysis frame derived from the cleaned jobs frame."""
    if df.empty:
        return pd.DataFrame(columns=ANALYSIS_COLUMNS)

    out = df.copy()
    add_role_class(out)

    matches = [
        find_ai_skills(f"{t}. {d}")
        for t, d in zip(out["title"].fillna(""), out["description"].fillna(""))
    ]
    out["ai_mentioned"] = [m.mentioned for m in matches]
    out["ai_total_mentions"] = [m.total_mentions for m in matches]
    for group, col in BY_GROUP_COLUMN_MAP.items():
        out[col] = [m.groups.get(group, 0) for m in matches]

    out["taxonomy_version"] = TAXONOMY_VERSION
    out["role_classifier_version"] = ROLE_CLASSIFIER_VERSION
    out = out[ANALYSIS_COLUMNS]

    # Keep only the columns DuckDB/analysis consumers need (drop the text heap
    # after flags are computed to keep exports lean) - but EDA likes the text.
    return out


__all__ = ["ANALYSIS_COLUMNS", "enrich_jobs_with_ai"]
