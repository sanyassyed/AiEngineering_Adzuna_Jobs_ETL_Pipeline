"""Offline stand-in for the Adzuna API.

Generates Adzuna-shaped data deterministically (seeded) so the pipeline can be
developed, tested, and demoed end-to-end without credentials. The data is made
"dirty" on purpose (string salaries, missing companies/coords, sloppy contract
fields, duplicate ad ids) so the cleaning + validation stages are exercised.

Ground-truth AI signal: descriptions are seeded with AI-skill phrases with a
probability that RISES between ``start_date`` and ``today`` - higher for
technical roles and with small country differences. Tests assert the analysis
layer recovers this encoded trend.
"""

from __future__ import annotations

import math
import random
from datetime import date, datetime, timedelta, timezone
from typing import Any, Optional

COMPANIES: list[str] = [
    "Acme Analytics Ltd", "Northern Star Consulting", "Bright Path Tech",
    "Capital & County", "Vertex Engineering", "Blue Harbour Group",
    "DataWise Solutions", "Sterling Retail Partners", "Skyline Logistics",
    "Meadowsoft", "Quantum Labs", "Juniper Health",
]

TITLES: list[str] = [
    "Senior Data Engineer", "Data Analyst", "Warehouse Operative",
    "Registered Nurse", "Software Developer", "Finance Manager",
    "Delivery Driver", "Marketing Executive", "Project Manager",
    "Customer Service Advisor", "Mechanical Engineer", "Teaching Assistant",
    "Accountant", "Product Designer", "DevOps Engineer", "Sales Executive",
]

CATEGORIES: list[tuple[str, str]] = [
    ("it-jobs", "IT Jobs"), ("accounting-finance-jobs", "Accounting & Finance Jobs"),
    ("healthcare-nursing-jobs", "Healthcare & Nursing Jobs"),
    ("logistics-warehouse-jobs", "Logistics & Warehouse Jobs"),
    ("retail-jobs", "Retail Jobs"), ("sales-jobs", "Sales Jobs"),
    ("engineering-jobs", "Engineering Jobs"), ("hr-jobs", "HR Jobs"),
    ("marketing-jobs", "Marketing Jobs"), ("teaching-jobs", "Teaching Jobs"),
]

TECH_CATEGORY_TAGS = {"it-jobs", "engineering-jobs"}

# (area hierarchy, display_name, lat, lon)
UK_LOCATIONS: list[tuple[list[str], str, float, float]] = [
    (["UK", "South East", "Berkshire"], "Reading, Berkshire", 51.454, -0.978),
    (["UK", "Greater London", "London"], "London", 51.509, -0.118),
    (["UK", "West Midlands", "Birmingham"], "Birmingham", 52.486, -1.890),
    (["UK", "Scotland", "Glasgow"], "Glasgow", 55.864, -4.251),
    (["UK", "North West", "Manchester"], "Manchester", 53.480, -2.242),
    (["UK", "Yorkshire"], "Leeds, Yorkshire", 53.800, -1.549),
    (["UK", "South West", "Bristol"], "Bristol", 51.454, -2.588),
    (["UK", "East Midlands", "Nottingham"], "Nottingham", 52.955, -1.149),
]

US_LOCATIONS: list[tuple[list[str], str, float, float]] = [
    (["US", "New York", "New York City"], "New York, NY", 40.713, -74.006),
    (["US", "California", "San Francisco"], "San Francisco, CA", 37.775, -122.419),
    (["US", "Texas", "Austin"], "Austin, TX", 30.267, -97.743),
    (["US", "Washington", "Seattle"], "Seattle, WA", 47.606, -122.332),
    (["US", "Illinois", "Chicago"], "Chicago, IL", 41.878, -87.630),
    (["US", "Massachusetts", "Boston"], "Boston, MA", 42.360, -71.058),
    (["US", "Georgia", "Atlanta"], "Atlanta, GA", 33.749, -84.388),
]

LOCATIONS_BY_COUNTRY: dict[str, list[Any]] = {
    "gb": UK_LOCATIONS,
    "us": US_LOCATIONS,
}

# AI phrases seeded into mock descriptions (taxonomy-aware).
AI_PHRASES: dict[str, list[str]] = {
    "general_ai": ["AI", "ML", "artificial intelligence", "data science"],
    "machine_learning": ["machine learning", "natural language processing", "computer vision"],
    "ml_tools": ["TensorFlow", "PyTorch", "scikit-learn", "Hugging Face"],
    "generative_ai": ["LLMs", "ChatGPT", "generative AI", "LangChain", "RAG", "prompt engineering"],
}
AI_PHRASE_POOL: list[str] = [p for group in AI_PHRASES.values() for p in group]

CONTRACT_TYPES = ["full_time", "part_time"]
CONTRACT_TIMES = ["permanent", "contract"]

# Encoded ground-truth parameters (documented; mirrors the analysis goal).
AI_BASE_PROB_TECHNICAL = 0.10
AI_RISE_TECHNICAL = 0.35
AI_BASE_PROB_NON_TECHNICAL = 0.02
AI_RISE_NON_TECHNICAL = 0.12
AI_COUNTRY_BUMP = {"us": 0.04, "gb": 0.02}


def ai_mention_probability(country: str, category_tag: str, created: datetime,
                           start: datetime, today: datetime) -> float:
    """Ground-truth probability used to seed AI phrases (public for tests)."""
    span = max((today - start).days, 1)
    maturity = max((created - start).days, 0) / span
    technical = category_tag in TECH_CATEGORY_TAGS
    base = AI_BASE_PROB_TECHNICAL if technical else AI_BASE_PROB_NON_TECHNICAL
    rise = AI_RISE_TECHNICAL if technical else AI_RISE_NON_TECHNICAL
    return min(max(base + rise * maturity + AI_COUNTRY_BUMP.get(country, 0.0), 0.0), 1.0)


class MockAdzunaClient:
    """Deterministic fake of :class:`adzuna_etl.api_client.AdzunaApiClient`.

    Implements ``fetch_page`` and ``fetch_history`` with the same signatures as
    the real client so the extract stage is interchangeable.
    """

    def __init__(
        self,
        *,
        start_date: str = "2026-01-01",
        rows_per_country: int = 2500,
        countries: tuple[str, ...] = ("gb", "us"),
        seed: int = 42,
        today: Optional[datetime] = None,
    ) -> None:
        self.start = datetime.combine(
            date.fromisoformat(start_date), datetime.min.time(), tzinfo=timezone.utc
        )
        self.today = today or datetime.now(timezone.utc)
        self.rows_per_country = rows_per_country
        self.countries = countries
        self.seed = seed
        self._state: dict[str, list[dict[str, Any]]] = {}

    # -- context manager (mirror real client) ----------------------------------
    def close(self) -> None:  # no-op
        return None

    def __enter__(self) -> "MockAdzunaClient":
        return self

    def __exit__(self, *exc_info: Any) -> None:
        self.close()

    # -- API surface ------------------------------------------------------------
    def fetch_page(self, country: str, page: int, *, results_per_page: int = 50,
                   max_days_old: int = 45) -> dict[str, Any]:
        ads = self._countries()[country]
        start = (page - 1) * results_per_page
        chunk = ads[start : start + results_per_page]
        return {
            "count": len(ads),
            "what": "",
            "where": "",
            "results_per_page": results_per_page,
            "page": page,
            "results": chunk if chunk else [],
        }

    def fetch_history(self, country: str) -> dict[str, Any]:
        rng = random.Random(self.seed + 999_001)
        base = rng.randint(2_000, 5_000)
        mean_salary = rng.randint(30_000, 45_000)
        history: dict[str, dict[str, int]] = {}
        span = max((self.today - self.start).days, 1)
        for offset in range(span):
            day = (self.today - timedelta(days=offset)).date()
            if day >= self.start.date():
                noise = int(400 * math.sin(offset / 7.0)) + rng.randint(-200, 200)
                history[day.isoformat()] = {"count": max(base + noise, 100)}
        return {"count": sum(v["count"] for v in history.values()),
                "mean_salary": mean_salary, "history": history}

    # -- generator ---------------------------------------------------------------
    def _countries(self) -> dict[str, list[dict[str, Any]]]:
        for country in self.countries:
            if country not in self._state:
                self._state[country] = self._generate_country(country)
        return self._state

    def _generate_country(self, country: str) -> list[dict[str, Any]]:
        rng = random.Random(self.seed + sum(ord(c) for c in country))
        max_age_days = max((self.today - self.start).days, 1)
        offset = (self.countries.index(country) + 1) * 1_000_000
        ads = [self._make_ad(country, i, offset, rng, max_age_days)
               for i in range(self.rows_per_country)]
        for _ in range(int(self.rows_per_country * 0.03)):
            ads.append(dict(rng.choice(ads)))
        rng.shuffle(ads)
        return ads

    def _make_ad(self, country: str, index: int, id_offset: int,
                 rng: random.Random, max_age_days: int) -> dict[str, Any]:
        locations = LOCATIONS_BY_COUNTRY.get(country) or UK_LOCATIONS
        area, display_name, lat, lon = rng.choice(locations)
        cat_tag, cat_label = rng.choice(CATEGORIES)
        age_days = rng.randint(1, max_age_days)
        created = self.today - timedelta(days=age_days)
        dirty = rng.random() < 0.08

        salary_min = rng.choice([20_000, 25_000, 30_000, 35_000, 40_000, 50_000, 60_000, 80_000, 100_000])
        salary_max = salary_min + rng.randint(2_000, 40_000)
        if rng.random() < 0.10:
            salary_min = None

        prob = ai_mention_probability(country, cat_tag, created, self.start, self.today)
        description = (
            f"Join our growing team in {display_name}. "
            f"Salary dependent on experience. {salary_max} range."
        )
        if rng.random() < prob:
            phrase = rng.choice(AI_PHRASE_POOL)
            description += f" Ideal for someone comfortable with {phrase}."

        ad_id = str(id_offset + 100_000 + index * 7 + rng.randint(0, 5))
        return {
            "id": ad_id,
            "adref": f"adzuna-adref-{ad_id}",
            "title": rng.choice(TITLES),
            "description": description,
            "redirect_url": f"https://www.adzuna.co.uk/land/ad/{ad_id}",
            "salary_min": f"£{salary_min:,}" if dirty and salary_min else salary_min,
            "salary_max": salary_max,
            "salary_is_predicted": int(age_days > 30),
            "created": created.isoformat().replace("+00:00", "Z"),
            "category": {"tag": cat_tag, "label": cat_label},
            "company": ({"display_name": None} if rng.random() < 0.05
                        else {"display_name": rng.choice(COMPANIES)}),
            "location": {"area": area, "display_name": display_name},
            "latitude": lat if rng.random() > 0.05 else None,
            "longitude": lon,
            "contract_type": "Full_Time " if dirty else rng.choice(CONTRACT_TYPES),
            "contract_time": rng.choice(CONTRACT_TIMES),
            "country": country,
        }


__all__ = ["MockAdzunaClient", "ai_mention_probability"]
