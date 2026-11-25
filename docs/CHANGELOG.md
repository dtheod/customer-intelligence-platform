# Changelog

- **2026-11-23 · D1** — Project structure: `cip` package, Databricks bundle (schemas + raw volume), CI (ruff + pytest), central config with the temporal split.
- **2026-11-24 · D1** — Bronze ingestion: explicit schemas, header/corrupt/null/duplicate checks before write, `cip-ingest` serverless job. Loaded `cip.bronze.customers` (48,723) and `cip.bronze.transactions` (3,159,157). Dev target uses plain schema names.
- **2026-11-25 · D1** — EDA (`notebooks/eda.ipynb`, `docs/data.md`): gate passed; target changed to 60-day dormancy (30-day "churn" is 92% temporary); splits re-cut so label windows close before the next split; value = next-90-day volume (COP); 0.6% merchant-like accounts hold 44.5% of volume. Added `cip.dbx_sql` warehouse helper.
