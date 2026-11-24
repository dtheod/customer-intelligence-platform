# Customer Intelligence Platform

Who is likely to leave, how valuable are they, why, and what should we do?

Churn (30-day) × customer value (90-day) on the COFINFAD fintech dataset, built on Databricks
(PySpark features, Unity Catalog, MLflow, Model Serving) with a FastAPI gateway, MCP tools and a
LangGraph investigation agent on Kubernetes.

See [docs/PLAN.md](docs/PLAN.md) for the architecture, temporal design and build plan.

## Quickstart

```bash
make install        # uv sync --all-extras
make lint test      # ruff + fast tests
databricks auth login --host <workspace-url>
make validate deploy-dev   # creates schemas + raw volume in the dev target
```

## Layout

| Path | Purpose |
|---|---|
| `src/cip/` | Python package, built as a wheel and run by Databricks jobs |
| `databricks.yml`, `resources/` | Databricks Asset Bundle: schemas, volume, jobs, serving endpoint |
| `tests/` | unit / data / contract / api / agent tests; CI never uses real data |
| `infra/` | Dockerfiles and Helm chart for the app layer |
| `docs/` | plan, ADRs, changelog |

## Data

COFINFAD: Colombian Fintech Financial Analytics Dataset, Mendeley Data,
DOI [10.17632/mhb4zn3258.1](https://doi.org/10.17632/mhb4zn3258.1), CC BY 4.0.
