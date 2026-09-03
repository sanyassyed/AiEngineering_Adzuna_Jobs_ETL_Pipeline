"""Convience wrapper when the ``adzuna-etl`` console script is unavailable."""

from __future__ import annotations

from adzuna_etl.cli import main

if __name__ == "__main__":
    raise SystemExit(main())