.PHONY: install lint format test test-spark validate deploy-dev

install:            ## Install all extras + dev/notebook tools into .venv, register the notebook kernel
	uv sync --all-extras --all-groups
	uv run python -m ipykernel install --sys-prefix --name cip --display-name "cip (.venv)"

lint:
	uv run ruff check .
	uv run ruff format --check .

format:
	uv run ruff format .
	uv run ruff check --fix .

test:               ## Fast tests (no Spark, no workspace)
	uv run pytest -m "not spark and not databricks"

test-spark:         ## Spark transformation tests (needs Java 17)
	uv run pytest -m spark

validate:           ## Validate the Databricks bundle
	databricks bundle validate

deploy-dev:         ## Deploy schemas, volume, jobs and endpoint to the dev target
	databricks bundle deploy -t dev
