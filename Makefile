# Convenience wrappers around uv.
.PHONY: setup run run-mock test notebook eda clean

## Create the uv environment and install project + dev group
setup:
	uv sync

## Run the ETL against the live Adzuna API (reads .env)
run:
	uv run adzuna-etl

## Run the ETL against the local mock API (no credentials required)
run-mock:
	uv run adzuna-etl --mock --data-dir data

## Run the unit tests
test:
	uv run pytest

## Regenerate the EDA notebook from scripts/generate_eda_notebook.py
notebook:
	uv run python scripts/generate_eda_notebook.py

## Execute the EDA notebook end-to-end and save outputs inline
eda:
	uv run jupyter nbconvert --to notebook --execute --inplace notebooks/01_eda_and_cleaning.ipynb

clean:
	rm -rf data/raw/* data/processed/* .pytest_cache .ruff_cache *.egg-info dist build
	find . -type d -name __pycache__ -prune -exec rm -rf {} +