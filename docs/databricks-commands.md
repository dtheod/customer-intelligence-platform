# Databricks Command Log

Every command run against the Databricks workspace (CLI, bundle, SQL, or UI action), in order, with
what it did. Append new entries at the bottom of the log; keep the quick reference current.

- **Workspace:** `https://dbc-ab6a4b19-6fbf.cloud.databricks.com` (AWS, Premium)
- **CLI profile:** `cip-dev` (stored in `~/.databrickscfg`)
- **Run from:** the repo root, with `export DATABRICKS_CONFIG_PROFILE=cip-dev` (or `--profile cip-dev`)

**Effect** legend: 🔍 read-only · ✏️ creates/changes workspace objects · 💰 uses compute (billed)

---

## Quick reference

| Task | Command |
|---|---|
| Check who I'm logged in as | `databricks current-user me` |
| Validate bundle config | `databricks bundle validate -t dev` |
| Deploy code + resources | `databricks bundle deploy -t dev` |
| Run the bronze load | `databricks bundle run ingest -t dev` |
| List schemas | `databricks schemas list cip` |
| List files in the raw volume | `databricks fs ls dbfs:/Volumes/cip/raw/cofinfad/` |
| Upload a file to the volume | `databricks fs cp <local> dbfs:/Volumes/cip/raw/cofinfad/<name>` |
| Inspect a table | `databricks tables get cip.bronze.<table>` |

---

## Log

### 2026-11-24 · Workspace and Unity Catalog setup (done by you)

| # | Where | Command / action | Effect | What it did |
|---|---|---|---|---|
| 1 | Account console | Created Premium workspace on AWS | ✏️ | New workspace `dbc-ab6a4b19-6fbf`, Unity Catalog enabled. |
| 2 | SQL Editor | `CREATE CATALOG IF NOT EXISTS cip;` | ✏️ | Dev catalog. All dev schemas, tables, volumes and models live here. |
| 3 | SQL Editor | `CREATE CATALOG IF NOT EXISTS cip_staging;` | ✏️ | Staging catalog, used only by CI deploys. Kept separate so CI permissions can't touch dev. |
| 4 | SQL Warehouses UI | Created `cip-warehouse` (serverless, 2X-Small, auto-stop 10 min) | ✏️ | SQL compute for the gateway and dashboards. ID `99b8d4edafcc5e27`; the bundle resolves it by name. |
| 5 | Terminal | `brew tap databricks/tap && brew install databricks` | local | Installed Databricks CLI v1.27.0. |
| 6 | Terminal | `databricks auth login --host https://dbc-ab6a4b19-6fbf.cloud.databricks.com --profile cip-dev` | local | Browser OAuth login; saved profile `cip-dev` in `~/.databrickscfg`. Host must match `workspace.host` in `databricks.yml`. |

### 2026-11-24 · First bundle deploy (done by you)

| # | Command | Effect | What it did |
|---|---|---|---|
| 7 | `databricks bundle validate -t dev` | 🔍 | Checked `databricks.yml` + `resources/*.yml`, resolved `${var.catalog}` = `cip` and `warehouse_id` by name. Nothing created. |
| 8 | `databricks bundle deploy -t dev` | ✏️ | Built the `cip` wheel, uploaded it and the bundle files to `/Workspace/Users/<you>/.bundle/customer-intelligence-platform/dev/`. **Created 7 schemas** in `cip` (`raw`, `bronze`, `silver`, `gold`, `ml`, `serving`, `monitoring`) and the managed **volume** `cip.raw.cofinfad`. |

### 2026-11-24 · Upload raw data (done by you)

| # | Command | Effect | What it did |
|---|---|---|---|
| 9 | `databricks fs cp data/customer_data.csv dbfs:/Volumes/cip/raw/cofinfad/customer_data.csv` (or UI upload) | ✏️ | Uploaded the customer file (23.5 MB, 48,723 rows) to the raw volume. |
| 10 | `databricks fs cp data/transactions_data.csv dbfs:/Volumes/cip/raw/cofinfad/transactions_data.csv` (or UI upload) | ✏️ | Uploaded the transactions file (119 MB, 3,159,157 rows) to the raw volume. |

### 2026-11-24 · Checks and bronze ingestion (done by Claude)

| # | Command | Effect | What it did |
|---|---|---|---|
| 11 | `databricks bundle validate -t dev -o json` | 🔍 | Confirmed plain schema names after removing `mode: development` from the dev target (`cip.raw`, not `cip.dev_<user>_raw`). Confirmed host/profile match and that you are in the `admins` group. |
| 12 | `databricks schemas list cip` | 🔍 | Confirmed the 7 schemas exist (plus the built-in `default` and `information_schema`). |
| 13 | `databricks volumes list cip raw` | 🔍 | Confirmed `cip.raw.cofinfad` exists (MANAGED). |
| 14 | `databricks fs ls -l dbfs:/Volumes/cip/raw/cofinfad/` | 🔍 | Confirmed both CSVs were uploaded, with the expected sizes. |
| 15 | `databricks bundle validate -t dev` | 🔍 | Validated the new `resources/jobs/ingest.yml` job definition. |
| 16 | `databricks bundle deploy -t dev` | ✏️ | Rebuilt the wheel with a unique version (`dynamic_version`), uploaded it, and **created the job `cip-ingest`** (ID `803143844858235`). Schemas and volume unchanged. |
| 17 | `databricks bundle run ingest -t dev` | 💰 ✏️ | Ran `cip-ingest` on serverless (~1 min, [run 710520457644708](https://dbc-ab6a4b19-6fbf.cloud.databricks.com/jobs/803143844858235/runs/710520457644708?o=7474657920848508)). Checked headers, parse errors, null keys and duplicates, then **created `cip.bronze.customers`** (48,723 rows) and **`cip.bronze.transactions`** (3,159,157 rows). All checks returned 0. |
| 18 | `databricks tables get cip.bronze.transactions` / `… customers` | 🔍 | Confirmed both are Delta tables with the declared types (`customer_id` LONG, `date` DATE, `amount` DECIMAL, …) plus `_corrupt_record`, `_source_file`, `_ingested_at`. |

### 2026-11-25 · Exploratory analysis (done by Claude)

| # | Command | Effect | What it did |
|---|---|---|---|
| 19 | ~30 `SELECT` queries on `cip.bronze.*` through `cip-warehouse`, from Python (`cip.dbx_sql`, auth via the `cip-dev` profile) and from `notebooks/eda.ipynb` | 🔍 💰 | Read-only aggregations (coverage, monthly activity, gaps between transactions, label horizons, dormancy drivers, column audit, amounts, value target). Woke the serverless warehouse (auto-stops after 10 min). No tables created or changed. Findings: [docs/data.md](data.md). |

### 2026-11-25 · Hands-on SQL exploration (done by you)

| # | Where | Command / action | Effect | What it did |
|---|---|---|---|---|
| 20 | SQL Editor on `cip-warehouse` | 14 read-only query sets on `cip.bronze.*`: table description and history, size and joins, monthly activity, transaction types, per-customer activity, gaps between transactions, dormancy label at 31 Jul, dormancy by activity decile, attributes vs dormancy, `churn_probability` correlations, full-year column check, survey timing, 90-day value target, one customer's history | 🔍 💰 | Re-checked the EDA findings by hand. Results matched [docs/data.md](data.md); nothing new found. No tables created or changed. |
