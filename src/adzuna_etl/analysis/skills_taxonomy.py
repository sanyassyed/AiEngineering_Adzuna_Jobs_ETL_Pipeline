"""Versioned AI-skills taxonomy used to scan job descriptions.

This is a curated dictionary (not an ML model) so every analysis result is
reproducible and auditable. Bump ``TAXONOMY_VERSION`` whenever entries are
added or removed; outputs stamp the version used.

Matching rules (see ``extract_skills``):
  * bare acronyms (AI, ML) are matched on word boundaries only (\bai\b) so
    words like *aim*, *email*, *available*, *detail* never trigger a hit;
  * phrases are matched case-insensitively; longer phrases match first so
    e.g. "large language model" is counted as that term, not "ai".
"""

from __future__ import annotations

import re

# Version that must be bumped when the taxonomy changes.
TAXONOMY_VERSION = "1.0"

AI_SKILL_GROUPS: dict[str, list[str]] = {
    "general_ai": [
        "artificial intelligence",
        "ai",
        "ml",
        "data science",
        "automation",
        "smart automation",
        "ai-powered",
    ],
    "machine_learning": [
        "machine learning",
        "deep learning",
        "neural network",
        "neural networks",
        "natural language processing",
        "nlp",
        "computer vision",
        "reinforcement learning",
        "predictive modeling",
        "predictive modelling",
        "recommendation system",
        "data mining",
        "forecasting",
    ],
    "ml_tools": [
        "tensorflow",
        "pytorch",
        "scikit-learn",
        "sklearn",
        "keras",
        "xgboost",
        "lightgbm",
        "hugging face",
    ],
    "generative_ai": [
        "generative ai",
        "genai",
        "large language model",
        "large language models",
        "llm",
        "llms",
        "foundation model",
        "openai",
        "chatgpt",
        "gpt-4",
        "gpt-5",
        "claude",
        "gemini",
        "copilot",
        "langchain",
        "retrieval augmented generation",
        "rag",
        "vector database",
        "vector db",
        "prompt engineering",
        "stable diffusion",
        "midjourney",
    ],
}

# Column names used in the DuckDB analysis table / export-friendly files.
BY_GROUP_COLUMN_MAP: dict[str, str] = {
    "general_ai": "ai_general_ai",
    "machine_learning": "ai_machine_learning",
    "ml_tools": "ai_ml_tools",
    "generative_ai": "ai_generative_ai",
}

_TERM_TO_GROUP: dict[str, str] = {
    term: group for group, terms in AI_SKILL_GROUPS.items() for term in terms
}


def build_skill_pattern() -> re.Pattern:
    """Compile one case-insensitive regex over the whole taxonomy."""
    parts = sorted(_TERM_TO_GROUP, key=len, reverse=True)
    return re.compile(
        "|".join(r"\b" + re.escape(t) + r"\b" for t in parts),
        re.IGNORECASE,
    )


SKILL_PATTERN = build_skill_pattern()


def group_of(term: str) -> str:
    return _TERM_TO_GROUP[term]


__all__ = [
    "AI_SKILL_GROUPS",
    "BY_GROUP_COLUMN_MAP",
    "SKILL_PATTERN",
    "TAXONOMY_VERSION",
    "build_skill_pattern",
    "group_of",
]
