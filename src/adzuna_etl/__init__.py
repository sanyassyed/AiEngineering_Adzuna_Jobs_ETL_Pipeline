"""adzuna-etl: ETL pipeline for Adzuna job data.

Layers: extract (Adzuna API) -> clean -> validate -> load (CSV).
Designed so later phases (incremental warehouse loads, SCD dimensional
modelling, visualisation) can be added without reshaping the data contract.
"""

from __future__ import annotations

__version__ = "0.1.0"
__all__ = ["__version__"]