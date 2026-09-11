"""Text-driven labour-market analysis over the cleaned job data.

The analytical goal (phase 1): measure how often job descriptions ask for AI
skills, split by technical / non-technical role class and by country, and
assess whether that demand is increasing over the available window.

All analysis is deterministic and rule-based (curated taxonomy + regex) so
results are auditable and reproducible - no trained model is involved.
"""

from __future__ import annotations

from adzuna_etl.analysis.classify_roles import add_role_class, classify_role
from adzuna_etl.analysis.enrich import enrich_jobs_with_ai
from adzuna_etl.analysis.extract_skills import SkillMatch, find_ai_skills
from adzuna_etl.analysis.skills_taxonomy import (
    AI_SKILL_GROUPS,
    BY_GROUP_COLUMN_MAP,
    TAXONOMY_VERSION,
    build_skill_pattern,
)
from adzuna_etl.analysis.trend import linear_trend, trend_series

__all__ = [
    "AI_SKILL_GROUPS",
    "BY_GROUP_COLUMN_MAP",
    "SkillMatch",
    "TAXONOMY_VERSION",
    "add_role_class",
    "build_skill_pattern",
    "classify_role",
    "enrich_jobs_with_ai",
    "find_ai_skills",
    "linear_trend",
    "trend_series",
]
