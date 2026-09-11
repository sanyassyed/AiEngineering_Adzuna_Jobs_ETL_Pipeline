"""Deterministic technical / non-technical role classification.

Primary signal: Adzuna category labels. Secondary signal: high-signal title
keywords for ads whose category is missing or ambiguous.

The mapping is explicit and versioned in this module so it can be reviewed and
refined (bump ``ROLE_CLASSIFIER_VERSION`` when it changes).
"""

from __future__ import annotations

import re

import pandas as pd

# Bump when the mapping logic changes; recorded in analysis outputs.
ROLE_CLASSIFIER_VERSION = "1.0"

TECHNICAL_TECH_TAGS: set[str] = {"it-jobs", "engineering-jobs"}

# Keywords that mark a title as technical when the category is missing/ambiguous.
_TECHNICAL_TITLE = re.compile(
    r"\b(engineer\w*|developer\b|programmer\b|software\b|devops\b|sre\b|"
    r"architect\b|data\w*|scientist\b|analyst\b|ml\b|ai\b|backend\b|frontend\b|"
    r"full[- ]?stack\b|platform\b|cloud\b|infrastructure\b|cyber\b|"
    r"python\b|sql\b|java\b|machine[- ]?learning\b|nlp\b)\b",
    re.IGNORECASE,
)

ROLE_NON_TECHNICAL = "non-technical"
ROLE_TECHNICAL = "technical"
ROLE_UNKNOWN = "unknown"


def _clean(value: object) -> str:
    return str(value).strip().lower() if value is not None else ""


def classify_role(category_tag: object, title: object) -> str:
    """Classify one ad into technical / non-technical."""
    tag = _clean(category_tag)
    title_text = _clean(title)
    if tag in TECHNICAL_TECH_TAGS:
        return ROLE_TECHNICAL
    if title_text and _TECHNICAL_TITLE.search(title_text):
        return ROLE_TECHNICAL
    if tag:
        return ROLE_NON_TECHNICAL
    return ROLE_UNKNOWN if not title_text else ROLE_NON_TECHNICAL


def add_role_class(df: pd.DataFrame) -> pd.DataFrame:
    """Add a ``role_class`` column to a cleaned jobs frame (in place)."""
    df["role_class"] = [
        classify_role(tag, title)
        for tag, title in zip(df["category_tag"], df["title"])
    ]
    return df


__all__ = [
    "ROLE_CLASSIFIER_VERSION",
    "ROLE_NON_TECHNICAL",
    "ROLE_TECHNICAL",
    "ROLE_UNKNOWN",
    "add_role_class",
    "classify_role",
]
