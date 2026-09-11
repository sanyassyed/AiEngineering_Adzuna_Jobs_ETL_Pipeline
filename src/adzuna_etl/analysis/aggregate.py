"""Aggregate AI-skill mention flags into review/export-ready summaries.

Every aggregation keeps a clear denominator (``total_ads``) so changes in ad
volume never get confused with changes in the *share* of ads mentioning AI.
"""

from __future__ import annotations

import pandas as pd


def _ensure_analysis_columns(df: pd.DataFrame) -> pd.DataFrame:
    if "role_class" not in df:
        raise ValueError("analysis frame is missing 'role_class' (run enrich_jobs_with_ai first)")
    if "ai_mentioned" not in df:
        raise ValueError("analysis frame is missing 'ai_mentioned'")
    out = df.copy()
    out["week"] = out["created_at"].dt.to_period("W").astype(str)
    return out


def weekly_share(df: pd.DataFrame) -> pd.DataFrame:
    """Weekly AI-mention share by (week, country, role_class)."""
    df = _ensure_analysis_columns(df)
    grouped = (
        df.groupby(["week", "country", "role_class"], as_index=False)
        .agg(total_ads=("job_id", "count"), ai_ads=("ai_mentioned", "sum"))
        .dropna(subset=["country"])
    )
    grouped["ai_share"] = grouped["ai_ads"] / grouped["total_ads"]
    return grouped.sort_values(["week", "country", "role_class"]).reset_index(drop=True)


def latest_share(df: pd.DataFrame) -> pd.DataFrame:
    """The most recent week's share by (country, role_class) + overall."""
    weekly = weekly_share(df)
    if weekly.empty:
        return weekly
    latest_week = weekly["week"].max()
    return weekly[weekly["week"] == latest_week].reset_index(drop=True)


def skill_counts(df: pd.DataFrame) -> pd.DataFrame:
    """Sum the per-group mention counts by country / role_class."""
    group_cols = [
        "ai_general_ai", "ai_machine_learning", "ai_ml_tools", "ai_generative_ai",
    ]
    out = (
        df.groupby(["country", "role_class"], as_index=False)[
            group_cols
        ]
        .sum()
        .dropna(subset=["country"])
    )
    out["ads"] = df.groupby(["country", "role_class"], as_index=False).size()["size"]
    return out.sort_values(["country", "ads"], ascending=[True, False]).reset_index(drop=True)


__all__ = ["latest_share", "skill_counts", "weekly_share"]
