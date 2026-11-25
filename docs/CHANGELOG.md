# Changelog

- **2026-11-23 · D1** — Project structure: `cip` package, Databricks bundle (schemas + raw volume), CI (ruff + pytest), central config with the temporal split.
- **2026-11-24 · D1** — Bronze ingestion: explicit schemas, header/corrupt/null/duplicate checks before write, `cip-ingest` serverless job. Loaded `cip.bronze.customers` (48,723) and `cip.bronze.transactions` (3,159,157). Dev target uses plain schema names.
