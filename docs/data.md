# Data: COFINFAD findings and decisions

Source: COFINFAD, Colombian Fintech Financial Analytics Dataset (Mendeley Data,
DOI [10.17632/mhb4zn3258.1](https://doi.org/10.17632/mhb4zn3258.1), CC BY 4.0).
Evidence: [`notebooks/eda.ipynb`](../notebooks/eda.ipynb), run 2026-11-25 against `cip.bronze.*`.

## Summary

| Question | Answer | Decision |
|---|---|---|
| Usable dates, clean joins? | Yes. Daily dates 4 Jan – 29 Dec 2023; 0 orphan transactions; 0 duplicate customers | **Day-1 gate passed** |
| Does 30-day churn make sense? | No. ~20% of active customers go 30 days without a transaction, and **92%** of them come back | Target changed to **60-day dormancy** |
| What predicts dormancy? | Transaction frequency and recency. Customer attributes (satisfaction, segment, tickets, provided churn score) are flat once frequency is held fixed | Behavioural features first; snapshot features evaluated with/without |
| Can provided columns be used? | `churn_probability` is a formula over snapshot fields (r = −0.88 with `active_products`, 0.01 with recency); `tx_count`/`first_tx`/`last_tx` are exact full-year aggregates | Excluded (list below) |
| Value target? | No revenue/fee field. Next-90-day volume: 1.5% zeros, log-corr with trailing volume 0.52 | **Next-90-day transaction volume (COP)**, baseline = trailing 90 days |
| Anything unusual? | 308 accounts (0.6%) have >1,000 transactions/year and **44.5% of all volume** | Log/Tweedie value model; metrics reported with and without them |
| Real or synthetic? | Flat monthly activity, identical satisfaction/NPS every quarter, attributes unrelated to behaviour | Very likely synthetic; stated openly as a limitation |

## Population

- 48,723 customers, 3,159,157 transactions (Transfer 45%, Payment 31%, Withdrawal 14%, Deposit 9%).
- ~263k transactions and ~39k active customers every month; no seasonality or trend.
- 78% of customers transact in January: existing customers whose pre-2023 history is missing, so
  tenure from first observed transaction is capped for most customers.

## Target: 60-day dormancy

**Definition.** At month-end cutoff `t`:
- population: customers with ≥ 1 transaction in `(t − 90d, t]`
- `dormant = 1` if the customer has **no transaction in `(t, t + 60d]`**

**Why 60 days, not 30:**

| Horizon | Positive rate | Positives who transact again within the next 60 days |
|---|---|---|
| 30 days | 19.9% | 92.3% |
| 45 days | 10.5% | 92.5% |
| **60 days** | **5.5%** | 92.7% |
| 90 days | 1.5% | 94.3% |

Gaps between a customer's transactions: median 1 day, p90 15, p95 27, **p99 60**. A 30-day pause
is normal behaviour for low-frequency customers; 60 days is beyond the 99th percentile.

**Framing.** Almost no one leaves permanently, so the product predicts **dormancy (reactivation
risk)**. Retention priority = P(dormant 60d) × expected 90-day volume = *volume at risk*.

**Signal.** At the validation cutoff (31 Jul), dormancy ranges from ~8% in the lowest-frequency
deciles to 0% in the top decile, and rises with days since last transaction. Expect a model driven
by recency/frequency/trend features; customer attributes add little.

## Temporal splits

Rule: every label window closes on or before the next split's cutoff (enforced by
`tests/unit/test_config.py`).

| Split | Dormancy cutoffs (60d) | Value cutoffs (90d) | Dormancy rate |
|---|---|---|---|
| Train | 31 Mar, 30 Apr, 31 May | 31 Mar | 5.64%, 5.47%, 5.52% |
| Validation | 31 Jul | 30 Jun | 5.64% |
| Test | 30 Sep | 30 Sep | 5.68% |
| Monitoring reference | 31 Oct (label window ends at data end) | – | 5.87% |
| Monitoring current | 30 Nov (no labels yet, as in production) | – | – |

~48k active customers per cutoff → ~144k training rows, ~8k positives.

## Column classification

| Class | Columns | Use |
|---|---|---|
| Behaviour (derived) | built from `bronze.transactions` as of each cutoff | Main features |
| Profile | age, gender, location, income_bracket, occupation, education_level, marital_status, household_size, acquisition_channel | Features |
| Dated snapshot | satisfaction_score, nps_score, base/tx/product_satisfaction (dated by `last_survey_date`) | Feature only if `last_survey_date <= cutoff`, else null |
| Undated snapshot | product flags, active_products, app_logins_frequency, feature_usage_diversity, credit_utilization_ratio, support_tickets_count, resolved_tickets_ratio, failed/international transactions, app_store_rating, feedback_sentiment, feature_requests, complaint_topics | `static_snapshot`; model trained with and without |
| **Never used** | churn_probability, customer_lifetime_value, clv_segment, customer_segment, tx_count, avg_tx_value, total_tx_volume, first_tx, last_tx, monthly_transaction_count, average_transaction_value, total_transaction_volume, transaction_frequency, last_transaction_date, first_transaction_date, preferred_transaction_type, weekend_transaction_ratio, avg_daily_transactions, customer_tenure | Full-year aggregates (future information) or provided model outputs |

`last_transaction_date` disagrees with `last_tx` for 96% of customers; it is unreliable as well as
leaky.

## Amounts and value

- All amounts positive; heavily right-skewed: median ~1.8M COP, p99 ~35M COP, max 690M COP.
- June and August each have ~190 transactions above 100M COP vs ~70 in other months (volume
  spikes); a drift-monitoring example to keep in mind.
- No revenue or fee field, so value = total transaction volume regardless of direction.
- Merchant-like accounts: median customer 18 transactions/year, p99 628, max 77,465; 308
  accounts with >1,000 transactions hold 44.5% of volume (top account 8.5%). Add a trailing-90d
  `high_volume_account` feature.

## Limitations to state in the README

1. Very likely synthetic: behaviour is independent of customer attributes, so explanations will
   centre on activity patterns.
2. No permanent churn signal; the product predicts dormancy.
3. No pre-2023 history: tenure is left-censored.
4. Value is volume, not revenue.
