"""Detect AI-skill mentions inside free-text job descriptions.

Pure, deterministic rules: normalise the text, then run the taxonomy regex
(located in ``skills_taxonomy``) over it and tally per-group / per-term hits.
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass, field
from typing import Any, Optional

from adzuna_etl.analysis.skills_taxonomy import (
    SKILL_PATTERN,
    TAXONOMY_VERSION,
    group_of,
)

_TAG_RE = re.compile(r"<[^>]+>")
_WS_RE = re.compile(r"\s+")
_CTRL_RE = re.compile(r"[\x00-\x1f\x7f]")


@dataclass
class SkillMatch:
    """Result of scanning one text value."""

    mentioned: bool = False
    total_mentions: int = 0
    groups: dict[str, int] = field(default_factory=dict)
    terms: dict[str, int] = field(default_factory=dict)


def normalize_text(value: Any) -> str:
    """Normalize free text for matching (does not destroy the source)."""
    if value is None:
        return ""
    text = str(value)
    text = unicodedata.normalize("NFKD", text)
    text = _TAG_RE.sub(" ", text)  # strip html/markup fragments
    text = text.replace("\u00a0", " ").replace("&nbsp;", " ")
    text = _CTRL_RE.sub(" ", text)
    text = _WS_RE.sub(" ", text)
    return text.strip().lower()


def find_ai_skills(text: Any) -> SkillMatch:
    """Return a :class:`SkillMatch` for one description/title value."""
    normalized = normalize_text(text)
    if not normalized:
        return SkillMatch()
    groups: dict[str, int] = {}
    terms: dict[str, int] = {}
    for match in SKILL_PATTERN.finditer(normalized):
        term = match.group().strip().lower()
        groups[group_of(term)] = groups.get(group_of(term), 0) + 1
        terms[term] = terms.get(term, 0) + 1
    return SkillMatch(
        mentioned=len(terms) > 0,
        total_mentions=sum(terms.values()),
        groups=groups,
        terms=terms,
    )


def term_counts_from(jobs: list[dict[str, Any]]) -> dict[str, int]:
    """Aggregate matched term counts across many raw/cleaned job rows."""
    totals: dict[str, int] = {}
    for job in jobs:
        desc = job.get("description") or ""
        title = job.get("title") or ""
        match = find_ai_skills(f"{title}. {desc}")
        for term, count in match.terms.items():
            totals[term] = totals.get(term, 0) + count
    return totals


__all__ = ["SkillMatch", "TAXONOMY_VERSION", "find_ai_skills", "normalize_text", "term_counts_from"]
