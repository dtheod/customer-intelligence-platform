"""Explicit source schemas for the COFINFAD CSVs. Never rely on schema inference for ingestion.

Column groups in the customer file (see docs/PLAN.md section 0):
- profile: static demographics, safe as features
- snapshot: measured at an unknown date, flagged as static_snapshot features
- full_year: aggregates over all of 2023 (incl. the future) and provided targets; ingested for
  lineage and EDA only, never used as features or labels
"""

from pyspark.sql.types import (
    BooleanType,
    DateType,
    DecimalType,
    DoubleType,
    IntegerType,
    LongType,
    StringType,
    StructField,
    StructType,
)

CORRUPT_RECORD_COL = "_corrupt_record"


def _f(name: str, dtype, nullable: bool = True) -> StructField:
    return StructField(name, dtype, nullable)


TRANSACTIONS_SCHEMA = StructType(
    [
        _f("customer_id", LongType(), nullable=False),
        _f("date", DateType(), nullable=False),
        _f("amount", DecimalType(18, 2), nullable=False),  # COP
        _f("type", StringType(), nullable=False),
    ]
)

CUSTOMER_PROFILE_COLUMNS = [
    _f("customer_id", LongType(), nullable=False),
    _f("age", IntegerType()),
    _f("gender", StringType()),
    _f("location", StringType()),
    _f("income_bracket", StringType()),
    _f("occupation", StringType()),
    _f("education_level", StringType()),
    _f("marital_status", StringType()),
    _f("household_size", IntegerType()),
    _f("acquisition_channel", StringType()),
]

CUSTOMER_SNAPSHOT_COLUMNS = [
    _f("savings_account", BooleanType()),
    _f("credit_card", BooleanType()),
    _f("personal_loan", BooleanType()),
    _f("investment_account", BooleanType()),
    _f("insurance_product", BooleanType()),
    _f("active_products", IntegerType()),
    _f("app_logins_frequency", IntegerType()),
    _f("feature_usage_diversity", IntegerType()),
    _f("bill_payment_user", BooleanType()),
    _f("auto_savings_enabled", BooleanType()),
    _f("credit_utilization_ratio", DoubleType()),
    _f("international_transactions", IntegerType()),
    _f("failed_transactions", IntegerType()),
    _f("base_satisfaction", DoubleType()),
    _f("tx_satisfaction", DoubleType()),
    _f("product_satisfaction", DoubleType()),
    _f("satisfaction_score", IntegerType()),
    _f("nps_score", IntegerType()),
    _f("last_survey_date", DateType()),
    _f("support_tickets_count", IntegerType()),
    _f("resolved_tickets_ratio", DoubleType()),
    _f("app_store_rating", DoubleType()),
    _f("feedback_sentiment", StringType()),
    _f("feature_requests", StringType()),
    _f("complaint_topics", StringType()),
]

CUSTOMER_FULL_YEAR_COLUMNS = [
    _f("customer_segment", StringType()),
    _f("tx_count", IntegerType()),
    _f("avg_tx_value", DoubleType()),
    _f("total_tx_volume", LongType()),
    _f("first_tx", DateType()),
    _f("last_tx", DateType()),
    _f("clv_segment", StringType()),
    _f("monthly_transaction_count", DoubleType()),
    _f("average_transaction_value", DoubleType()),
    _f("total_transaction_volume", LongType()),
    _f("transaction_frequency", DoubleType()),
    _f("last_transaction_date", DateType()),
    _f("preferred_transaction_type", StringType()),
    _f("first_transaction_date", DateType()),
    _f("weekend_transaction_ratio", DoubleType()),
    _f("avg_daily_transactions", DoubleType()),
    _f("customer_tenure", DoubleType()),
    _f("churn_probability", DoubleType()),
    _f("customer_lifetime_value", DoubleType()),
]

# Order must match the CSV header exactly (CSV columns are positional).
CUSTOMER_COLUMN_ORDER = [
    "customer_id", "age", "gender", "location", "income_bracket", "occupation",
    "education_level", "marital_status", "household_size", "acquisition_channel",
    "customer_segment", "savings_account", "credit_card", "personal_loan", "investment_account",
    "insurance_product", "active_products", "app_logins_frequency", "feature_usage_diversity",
    "bill_payment_user", "auto_savings_enabled", "credit_utilization_ratio",
    "international_transactions", "failed_transactions", "tx_count", "avg_tx_value",
    "total_tx_volume", "first_tx", "last_tx", "base_satisfaction", "tx_satisfaction",
    "product_satisfaction", "satisfaction_score", "nps_score", "last_survey_date",
    "support_tickets_count", "resolved_tickets_ratio", "app_store_rating", "feedback_sentiment",
    "feature_requests", "complaint_topics", "clv_segment", "monthly_transaction_count",
    "average_transaction_value", "total_transaction_volume", "transaction_frequency",
    "last_transaction_date", "preferred_transaction_type", "first_transaction_date",
    "weekend_transaction_ratio", "avg_daily_transactions", "customer_tenure",
    "churn_probability", "customer_lifetime_value",
]  # fmt: skip

_by_name = {
    f.name: f
    for f in CUSTOMER_PROFILE_COLUMNS + CUSTOMER_SNAPSHOT_COLUMNS + CUSTOMER_FULL_YEAR_COLUMNS
}
CUSTOMERS_SCHEMA = StructType([_by_name[c] for c in CUSTOMER_COLUMN_ORDER])

FULL_YEAR_COLUMN_NAMES = frozenset(f.name for f in CUSTOMER_FULL_YEAR_COLUMNS)
SNAPSHOT_COLUMN_NAMES = frozenset(f.name for f in CUSTOMER_SNAPSHOT_COLUMNS)


def with_corrupt_record(schema: StructType) -> StructType:
    """Schema plus a column that captures rows Spark could not parse into the declared types."""
    return StructType([*schema.fields, StructField(CORRUPT_RECORD_COL, StringType(), True)])
