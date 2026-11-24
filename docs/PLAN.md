# Build Plan — Customer Intelligence Platform

**Window:** Mon 23 Nov → Fri 4 Dec 2026 (10 working days)
**Product question:** *Who is likely to leave, how valuable are they, why, and what should we do?*
**Primary flow:** churn (30d) × value (90d) → retention priority → SHAP drivers → agent investigation → recommendation.
**Secondary (stretch only):** anomaly detection.

**Platform split:**
- **Databricks = data + ML platform.** Ingestion, PySpark features, data quality, training, MLflow + Unity Catalog registry, **Model Serving endpoint**, batch scoring, drift monitoring, retraining jobs.
- **Kubernetes = application layer.** FastAPI business gateway, MCP server, LangGraph agent — consumers of the Databricks endpoint.

---

## Target architecture

```
                         DATABRICKS WORKSPACE (Unity Catalog: cip.*)
 ┌──────────────────────────────────────────────────────────────────────────────┐
 │  UC Volume (raw CSV) ─▶ bronze ─▶ silver ─▶ gold features (UC feature table)  │
 │                          PySpark jobs + DQ checks  (Lakeflow Job, bundle)     │
 │                                      │                                        │
 │                     point-in-time training set (FeatureLookup)                │
 │                                      │                                        │
 │             churn model   value model   ──▶  MLflow  ──▶  UC registry         │
 │                    └──────────┬───────┘          cip.ml.customer_intel@champion│
 │                 composite pyfunc: P(churn), E[value], priority, SHAP drivers  │
 │                                      │                                        │
 │                ┌─────────────────────┴───────────────┐                        │
 │       Model Serving endpoint                 Batch scoring job                │
 │       "customer-intelligence"                ─▶ cip.serving.customer_scores    │
 │                │ inference table                                              │
 │                ▼                                                              │
 │       Drift job (PSI/KS) ─▶ cip.monitoring.model_monitoring ─▶ retrain job    │
 └───────────────▲───────────────────────────────────▲──────────────────────────┘
                 │ REST (token)                      │ SQL warehouse
 ┌───────────────┴───────────────────────────────────┴──────────────────────────┐
 │  KUBERNETES (kind, via Helm)                                                  │
 │   FastAPI gateway  ◀── MCP server (customer.*, ml.* tools) ◀── LangGraph agent │
 └──────────────────────────────────────────────────────────────────────────────┘
```

---

## 0. Ground truth about the data (read first)

COFINFAD (Mendeley, DOI 10.17632/mhb4zn3258.1, CC BY 4.0):
- ~48.7k customers, ~3.16M transactions, **Jan–Dec 2023**, 57 variables.
- The customer table ships a **`churn_probability`** field. That is someone else's model output → **never used as a feature or a label** (leakage).
- Customer-level attributes (satisfaction, NPS, app engagement, product holdings) are most likely **end-of-period snapshots**, not time-stamped → leakage risk at earlier cutoffs.

**Decisions this forces:**
1. **Label from transactions:** `churned(c, t) = active(c, t) AND no transactions in (t, t+30d]`, where `active(c, t) = ≥1 transaction in (t−90d, t]`.
2. **Features tagged `temporal` vs `static_snapshot`** in the feature contract. Churn model trained with and without snapshot features; gap reported as a leakage upper bound.
3. **Monthly snapshots** (one row per customer per month-end cutoff):

   | Cutoffs | Role | Label window |
   |---|---|---|
   | Apr → Jul 2023 | train | next 30d |
   | Aug 2023 | validation | Sep |
   | Sep 2023 | test | Oct |
   | Oct 2023 | production month 1 — monitoring reference | Nov |
   | Nov 2023 | production month 2 — drift / degradation | Dec |

   Value target (next 90d) → value cutoffs end Sep 2023 (train Apr–Jun, val Jul, test Aug/Sep).

**Day-1 gate:** if transactions lack usable timestamps or customer IDs don't join, stop and re-plan.

---

## 1. Databricks design decisions

| Concern | Choice | Why |
|---|---|---|
| Workspace | Works on **Databricks Free Edition** (serverless only); paid workspace unlocks extras marked ⭐ | No cost to start; nothing in the critical path depends on paid features |
| Governance | Unity Catalog: catalog `cip` (configurable) with schemas `raw`, `bronze`, `silver`, `gold`, `ml`, `serving`, `monitoring` | Lineage, permissions, one namespace for data + models |
| Raw data | UC Volume `cip.raw.cofinfad` | Files governed like tables |
| Code → workspace | **Databricks Asset Bundles** (`databricks.yml`) with `dev` / `staging` targets; jobs, serving endpoint and schemas declared as resources | Infra-as-code for Databricks; `bundle deploy` from CI |
| Pipelines | Lakeflow Jobs (serverless) running Python wheel tasks from `src/cip` | Same reusable functions run in jobs, tests and Databricks Connect |
| Features | Gold table registered as **UC feature table** (PK `customer_id`, timeseries key `cutoff_date`); training via `FeatureLookup(timestamp_lookup_key=…)` | Point-in-time joins enforced by the platform, not by convention |
| Tracking / registry | Workspace MLflow; models in UC registry with aliases `champion` / `challenger` | Stages are legacy in UC; aliases drive deployment |
| **Endpoint** | One **Model Serving endpoint `customer-intelligence`** serving a composite `pyfunc`: churn model + value model + calibrator + SHAP explainer → returns probability, expected value, priority tier, top drivers | One governed decision endpoint (Free Edition caps endpoint count); both component models still versioned separately in UC |
| Endpoint input | Feature vector passed in the request (gateway looks it up from `gold` via SQL warehouse) | Online feature store isn't available on Free Edition. ⭐ Paid: publish features to the Lakebase **Online Feature Store** and the endpoint looks them up by `customer_id` automatically |
| Request logging | ⭐ AI Gateway **inference table** on the endpoint; Free Edition fallback: gateway writes request logs to a Delta table via SQL | Feeds drift monitoring with real serving traffic |
| Monitoring | Hand-written PSI/KS job → `cip.monitoring.model_monitoring` (Delta) + Databricks SQL dashboard; ⭐ Lakehouse Monitoring on the inference table as a comparison | Interview-explainable math; native dashboard |
| Retraining | Lakeflow Job: `drift_check` → **condition task** (`status == retrain_review`) → `train_challenger` → `compare` → manual alias promotion | Trigger is a real orchestrated path, not a script |
| Local dev | Databricks Connect (serverless) for interactive runs; local PySpark for unit tests | Fast tests without a workspace; same code runs remotely |

**App layer (unchanged tech, new role):**

| Concern | Choice |
|---|---|
| FastAPI gateway | Business API. Reads profile/features/scores from Databricks SQL warehouse (`databricks-sql-connector`), calls the serving endpoint (`databricks-sdk`), shapes responses with `contracts.py` |
| MCP | Python MCP SDK (FastMCP), streamable HTTP; tools proxy the gateway |
| Agent | LangGraph + Claude via `langchain-anthropic` (model id in config); Pydantic structured output |
| Infra | Docker, docker-compose (gateway + MCP only — no local Postgres/MLflow), Helm on **kind** |
| CI/CD | GitHub Actions: ruff → pytest → `databricks bundle validate` → deploy bundle to `staging` → endpoint smoke test → build images → Trivy → kind + Helm smoke test |

**Prerequisites:**
- Databricks workspace + CLI auth (`databricks auth login`), a serverless SQL warehouse.
- CI: service principal with OAuth M2M secret (`DATABRICKS_HOST`, `DATABRICKS_CLIENT_ID`, `DATABRICKS_CLIENT_SECRET` as GitHub secrets).
- Local: Java 17 (local PySpark tests), Helm (`brew install openjdk@17 helm`). Docker and kind already installed.

---

## 2. Repository layout

```
customer-intelligence-platform/
├── databricks.yml                 # bundle: targets dev/staging, variables (catalog, warehouse)
├── resources/                     # bundle resources
│   ├── schemas.yml
│   ├── jobs/{ingest,features,train,score,monitor,retrain}.yml
│   └── serving/customer_intelligence_endpoint.yml
├── src/cip/
│   ├── config.py                  # pydantic-settings; catalog, dates, thresholds
│   ├── contracts.py               # feature schema + endpoint/API/agent response models
│   ├── data/                      # ingest volume CSV → bronze Delta
│   ├── features/                  # build_*_features, build_target, snapshots, feature table registration
│   ├── quality/                   # schema + DQ checks, DQ report table
│   ├── models/                    # train_churn, train_value, evaluate, priority, explain, composite pyfunc
│   ├── scoring/                   # batch scoring job
│   ├── monitoring/                # psi/ks, calibration, drift job, retrain condition
│   ├── gateway/                   # FastAPI (calls Databricks)
│   ├── mcp_server/
│   └── agents/
├── notebooks/                     # EDA only, run on Databricks
├── tests/{unit,data,contract,api,agent}/ + fixtures/   # CI never touches real data
├── configs/                       # model params, thresholds, actions.yaml
├── infra/docker/                  # Dockerfile.gateway, Dockerfile.mcp
├── infra/helm/customer-intelligence/
├── docs/                          # PLAN.md, diagrams, ADRs, screenshots
├── .github/workflows/
├── docker-compose.yml
├── Makefile
└── pyproject.toml                 # builds the cip wheel used by bundle jobs
```

---

## 3. Day-by-day

Each day ends with: tests green, a commit, a one-line entry in `docs/CHANGELOG.md`.

### Week 1 — Databricks data + ML + endpoint

**D1 · Mon 23 Nov — Repo, workspace, data, problem definition**
- Scaffold repo, `pyproject.toml` (wheel build), ruff, pytest, Makefile; **CI skeleton** (ruff + pytest).
- Bundle skeleton: `databricks.yml`, `dev` target, schemas resource; `databricks bundle deploy -t dev` creates `cip.*` schemas + volume.
- Download COFINFAD → upload to volume → `ingest` job → bronze Delta.
- EDA notebook on Databricks: schema, date coverage, joins, monthly activity, base churn rate under our label. **Run the Day-1 gate.**
- README v0: business problem, target, temporal design, architecture diagram, licence attribution.
- ✅ Bronze tables in UC + documented target with measured base rate.

**D2 · Tue 24 Nov — PySpark feature pipeline + DQ (on Databricks)**
- `build_snapshots(cutoffs)` → `build_transaction_features` (count/amount 7/30/90d, recency, avg value, 30d-vs-prior-30d trend, product breadth), `build_engagement_features`, `build_customer_features` (tenure as-of + flagged snapshot fields), `build_target`.
- Every builder takes `(df, cutoff)` and filters `txn_ts <= cutoff` itself; unit test with a transaction one second after cutoff.
- DQ: schema, null thresholds, duplicate (customer, cutoff), impossible dates, negative amounts, feature ranges → `cip.monitoring.dq_results`; job fails on hard violations.
- Register `cip.gold.customer_features` as a UC feature table (PK + timeseries key); labels in `cip.gold.churn_labels`, `cip.gold.value_labels`.
- `features` job in bundle: silver → gold → DQ.
- ✅ `databricks bundle run features` produces governed feature + label tables.

**D3 · Wed 25 Nov — Churn model**
- Training set via `fe.create_training_set` with point-in-time `FeatureLookup`.
- Logistic regression baseline → LightGBM (CatBoost only if ahead).
- Metrics on test cutoff: PR-AUC, ROC-AUC, Precision/Recall@Top-10%, Lift@10%, Brier + calibration curve; isotonic calibration on validation.
- With/without snapshot features comparison.
- MLflow: params, features, dataset version (Delta table version), metrics, plots, model + signature → `cip.ml.churn_model@champion`.
- `train` job in bundle.
- ✅ Registered churn model; experiment comparing ≥2 models.

**D4 · Thu 26 Nov — Value model + decision layer**
- Target: revenue proxy or transaction value over next 90d (decided D1).
- Baseline: trailing-90d value. Model: LightGBM Tweedie → `cip.ml.value_model@champion`.
- `priority = P(churn) × E[value_90d]`; tiers by percentile (HIGH = top 10% expected loss).
- Headline: "contacting top 10% by priority captures X% of value-at-risk vs Y% ranking by churn alone."
- Batch scoring job → `cip.serving.customer_scores` (powers "who do we call today?").
- ✅ Value model + priority logic + headline metric + scores table.

**D5 · Fri 27 Nov — SHAP + composite model + Databricks Model Serving endpoint**
- `explain.py`: SHAP TreeExplainer → human sentences via feature templates.
- `CustomerIntelligenceModel(mlflow.pyfunc.PythonModel)`: loads churn + value + calibrator + explainer; input = feature rows; output = `{churn_probability, expected_90_day_value, priority, risk_level, top_drivers}` (schema from `contracts.py`). Registered as `cip.ml.customer_intelligence@champion`.
- Endpoint `customer-intelligence` declared in bundle (CPU small, scale-to-zero), served entity points at the alias's version.
- Contract test: query the endpoint with fixture rows, assert schema/bounds; local test of the pyfunc with `mlflow.pyfunc.load_model`.
- ✅ Live Databricks endpoint returning predictions + explanations. **End-of-week checkpoint.**

### Week 2 — App layer, agent, MCP, MLOps

**D6 · Mon 30 Nov — FastAPI gateway + Docker**
- Endpoints: `GET /health`, `/customer/{id}`, `/customer/{id}/churn`, `/value`, `/explanation`, `/customers/at-risk?top_k=`.
- `/customer/{id}/*`: fetch latest features from gold via SQL warehouse → call serving endpoint → shape response. `/at-risk` reads `customer_scores`.
- Request logging to Delta (Free Edition) or rely on inference table (⭐).
- Dockerfile (multi-stage, non-root), docker-compose (gateway + MCP), Databricks creds via env.
- Tests: `TestClient` with fake Databricks clients (no network in CI); input validation; 404/422/upstream-timeout handling.
- ✅ `docker compose up` → business API backed by Databricks.

**D7 · Tue 1 Dec — LangGraph agent + MCP**
- MCP tools: `customer.get_profile`, `customer.get_transactions`, `ml.get_churn_score`, `ml.get_value_score`, `ml.get_explanation`, `ml.list_at_risk` → all proxy the gateway (one governed path).
- Graph: `load_customer → assess_risk → retrieve_evidence → explain_drivers → recommend_action → validate → (retry once | END)`; tools loaded via `langchain-mcp-adapters`.
- LLM only in `explain_drivers` / `recommend_action`. `validate` is rule-based: schema parses, tiers match the endpoint's numbers, every cited number exists in evidence, action from `configs/actions.yaml`. One retry, then rule-based fallback.
- Tests: fake LLM + fake MCP; 5–10 scenario evals.
- README: Claude Desktop / Claude Code config pointing at the same MCP server (second consumer).
- ✅ `make agent CUSTOMER=38194` → validated structured recommendation via MCP.

**D8 · Wed 2 Dec — Monitoring + drift + retraining (on Databricks)**
- Reference = Oct-2023 scoring; current = Nov-2023 + `simulate_degradation` (engagement drop, injected missingness, shifted amounts).
- Drift job: per-feature PSI + KS, prediction PSI, missing rate, realised churn rate, calibration error, PR-AUC vs test → `cip.monitoring.model_monitoring` (timestamp, model_version, metric, feature, value, threshold, status).
- Rules: PSI < 0.1 healthy · 0.1–0.25 warning · > 0.25 retrain review.
- `retrain` job: drift task → condition task → train challenger → compare on latest labelled cutoff → set `@challenger`; promotion to `@champion` is a manual, documented step.
- Databricks SQL dashboard over monitoring + DQ tables; gateway exposes Prometheus `/metrics` (latency, errors, upstream endpoint latency).
- ✅ Dashboard showing healthy vs degraded runs + working retrain path.

**D9 · Thu 3 Dec — CI/CD + Kubernetes/Helm**
- Helm chart for gateway + MCP: Deployment, Service, ConfigMap (catalog, endpoint name, thresholds), Secret (Databricks token/OAuth, LLM key), probes (readiness checks endpoint reachability), resources, replicas, `values-staging.yaml`.
- GitHub Actions:
  1. ruff → unit/data/contract tests (local Spark, setup-java)
  2. `databricks bundle validate` → `bundle deploy -t staging` (on `main`) → endpoint smoke test
  3. build images → Trivy (fail on HIGH/CRITICAL)
  4. kind → `helm install` → smoke test `/health` + one `/customer/{id}/churn` against staging Databricks
- ✅ One pipeline deploys both the Databricks bundle and the app layer.

**D10 · Fri 4 Dec — Integration + polish**
- End-to-end demo: agent → MCP → gateway → SQL warehouse + serving endpoint → recommendation. Pre-warm the endpoint (scale-to-zero cold start).
- Two demo customers: HIGH-risk/HIGH-value vs HIGH-risk/LOW-value.
- README: diagram, quickstart, metrics, headline number, design decisions, limitations, future work.
- ADRs: label definition · snapshot features · composite endpoint vs per-model endpoints · request-time features vs online store · aliases vs stages · MCP-over-API.
- Screenshots (UC lineage, MLflow, endpoint, dashboard); 2–3 min demo video.

---

## 4. Cut lines

| At | If behind | Cut |
|---|---|---|
| End D2 | feature table registration fighting you | plain Delta table + manual point-in-time join (document it) |
| End D3 | no LightGBM in UC | CatBoost; snapshot comparison → README note |
| End D5 | composite pyfunc not serving | serve churn model alone; value + SHAP computed in gateway |
| End D7 | agent not via MCP | direct HTTP; MCP ships with one tool consumed |
| End D8 | retrain job not wired | drift job + manual `bundle run retrain` |
| End D9 | Helm not deploying | CI stops after bundle deploy + Trivy; Helm validated with `helm template` + `kubeconform` |

**Not in scope:** Temporal, Kafka, Lakeflow Declarative Pipelines, Vector Search, Databricks Apps, React, cloud K8s, Terraform, LLM UI, multi-agent.
**Stretch order:** anomaly detection → ⭐ Online Feature Store lookup → champion/challenger A/B traffic split on the endpoint → feedback loop → Streamlit.

---

## 5. Open decisions

1. **Workspace tier** — Free Edition (default plan) vs a trial/paid workspace. Paid enables online feature lookup, inference tables, Lakehouse Monitoring; plan works without them.
2. **Agent LLM** — Claude via Anthropic API (default) vs routing through a Databricks external-model endpoint / AI Gateway (one more governed endpoint, more setup).
3. **App layer host** — Kubernetes/Helm (default, matches target roles) vs Databricks Apps (simpler, but loses the K8s story).
4. **Value target** — decided D1 from available fields.
