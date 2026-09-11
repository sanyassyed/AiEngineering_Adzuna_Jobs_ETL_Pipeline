"""Trend estimation for the AI-skill weekly share series.

Fits a simple linear regression of weekly AI-mention share on time and reports
the slope in percentage-points per month with a 95% confidence interval and a
plain-language verdict (increasing / stable / decreasing).
"""

from __future__ import annotations

import numpy as np
import pandas as pd
from scipy import stats

# Weeks-per-month used to convert a weekly slope into a monthly slope.
WEEKS_PER_MONTH = 4.33


def _verdict(slope_pp_month: float, se_pp_month: float, p_value: float) -> str:
    if p_value > 0.05:
        return "stable"
    if slope_pp_month > 0:
        return "increasing"
    return "decreasing"


def linear_trend(weekly: pd.DataFrame, min_weeks: int = 3) -> pd.DataFrame:
    """Estimate the trend of ``ai_share`` over ``week`` per country x role_class.

    Expects columns: week, country, role_class, ai_share.
    """
    if weekly.empty:
        return pd.DataFrame()
    rows: list[dict] = []
    for (country, role_class), grp in weekly.groupby(["country", "role_class"]):
        grp = grp.sort_values("week").reset_index(drop=True)
        x = np.arange(len(grp))
        y = grp["ai_share"].astype(float).to_numpy()
        row = {
            "country": country,
            "role_class": role_class,
            "weeks": len(grp),
            "first_week": grp["week"].iloc[0],
            "last_week": grp["week"].iloc[-1],
            "week0_share": round(float(y[0]), 4),
            "weekN_share": round(float(y[-1]), 4),
        }
        if len(grp) < min_weeks:
            row.update(
                slope_pp_per_month=None, se_pp_per_month=None, p_value=None,
                ci_low_pp_per_month=None, ci_high_pp_per_month=None,
                verdict="insufficient_data",
            )
            rows.append(row)
            continue
        res = stats.linregress(x, y)
        slope_pp = res.slope * WEEKS_PER_MONTH * 100.0
        se_pp = res.stderr * WEEKS_PER_MONTH * 100.0
        row.update(
            slope_pp_per_month=round(slope_pp, 3),
            se_pp_per_month=round(se_pp, 3),
            p_value=round(float(res.pvalue), 4),
            ci_low_pp_per_month=round(slope_pp - 1.96 * se_pp, 3),
            ci_high_pp_per_month=round(slope_pp + 1.96 * se_pp, 3),
            verdict=_verdict(slope_pp, se_pp, float(res.pvalue)),
        )
        rows.append(row)
    return pd.DataFrame(rows)


def trend_series(weekly: pd.DataFrame, **kwargs) -> pd.DataFrame:
    """Alias kept for a stable public API."""
    return linear_trend(weekly, **kwargs)


__all__ = ["WEEKS_PER_MONTH", "linear_trend", "trend_series"]
