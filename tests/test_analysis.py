from __future__ import annotations

import numpy as np
import pandas as pd

from adzuna_etl.analysis.aggregate import weekly_share
from adzuna_etl.analysis.classify_roles import ROLE_NON_TECHNICAL, ROLE_TECHNICAL, classify_role
from adzuna_etl.analysis.extract_skills import find_ai_skills, normalize_text
from adzuna_etl.analysis.trend import linear_trend


def test_acronyms_match_only_on_word_boundaries():
    hit = find_ai_skills("We need experience with AI and ML pipelines.")
    assert hit.mentioned
    assert "ai" in hit.terms
    assert "ml" in hit.terms

    no_hit = find_ai_skills("Please aim for a good email layout; available skills matter.")
    assert not no_hit.mentioned


def test_phrase_matching_assigns_groups():
    hit = find_ai_skills("Deep learning plus LLMs required; also TensorFlow.")
    assert hit.mentioned
    assert hit.groups.get("machine_learning", 0) >= 1
    assert hit.groups.get("generative_ai", 0) >= 1
    assert hit.groups.get("ml_tools", 0) >= 1


def test_normalize_text_strips_markup_and_nbsp():
    assert normalize_text("<p>AI&nbsp;skills</p>") == "ai skills"


def test_classify_role():
    assert classify_role("it-jobs", "Software Developer") == ROLE_TECHNICAL
    assert classify_role("engineering-jobs", "Mechanical Engineer") == ROLE_TECHNICAL
    assert classify_role("marketing-jobs", "Marketing Executive") == ROLE_NON_TECHNICAL
    # Missing category -> high-signal title keyword rescues it.
    assert classify_role("", "Senior Data Scientist") == ROLE_TECHNICAL


def test_trend_detects_increasing_share():
    weeks = [f"2026-W{i:02d}" for i in range(1, 9)]
    shares = np.linspace(0.10, 0.45, 8)
    df = pd.DataFrame(
        {"week": weeks, "country": "gb", "role_class": "technical", "ai_share": shares}
    )
    out = linear_trend(df)
    assert len(out) == 1
    assert out.iloc[0]["verdict"] == "increasing"
    assert out.iloc[0]["slope_pp_per_month"] > 0
    assert out.iloc[0]["ci_low_pp_per_month"] > 0


def test_weekly_share_keeps_denominator():
    df = pd.DataFrame(
        {
            "job_id": ["a", "b", "c"],
            "country": ["gb", "gb", "gb"],
            "role_class": ["technical", "technical", "non-technical"],
            "created_at": pd.to_datetime(["2026-05-01", "2026-05-02", "2026-05-03"], utc=True),
            "ai_mentioned": [True, False, True],
        }
    )
    weekly = weekly_share(df)
    tech = weekly[(weekly["country"] == "gb") & (weekly["role_class"] == "technical")]
    assert int(tech.iloc[0]["total_ads"]) == 2
    assert int(tech.iloc[0]["ai_ads"]) == 1
    assert tech.iloc[0]["ai_share"] == 0.5
