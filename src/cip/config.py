"""Central configuration. Override any field with a CIP_-prefixed env var (e.g. CIP_CATALOG)."""

from datetime import date
from functools import lru_cache
from pathlib import Path

from pydantic import BaseModel, Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class TemporalDesign(BaseModel):
    """Month-end cutoffs and windows. See docs/PLAN.md section 0 and docs/data.md.

    Rule: every label window in a split closes on or before the next split's cutoff, so no
    model is trained on outcomes that would not yet be known at validation/test time.
    """

    data_start: date = date(2023, 1, 4)
    data_end: date = date(2023, 12, 29)

    lookback_days: int = 90
    active_window_days: int = 90
    # Dormancy, not 30-day churn: 92% of customers idle for 30 days return (docs/data.md).
    churn_horizon_days: int = 60
    value_horizon_days: int = 90

    churn_train: list[date] = [date(2023, 3, 31), date(2023, 4, 30), date(2023, 5, 31)]
    churn_validation: list[date] = [date(2023, 7, 31)]
    churn_test: list[date] = [date(2023, 9, 30)]

    value_train: list[date] = [date(2023, 3, 31)]
    value_validation: list[date] = [date(2023, 6, 30)]
    value_test: list[date] = [date(2023, 9, 30)]

    # Production simulation. Reference labels close at data_end; current has no labels yet,
    # as in real production, so only feature/prediction drift can be measured there.
    monitoring_reference: date = date(2023, 10, 31)
    monitoring_current: date = date(2023, 11, 30)


class DriftThresholds(BaseModel):
    psi_warning: float = 0.10
    psi_retrain: float = 0.25


_REPO_ENV = Path(__file__).resolve().parents[2] / ".env"  # works from notebooks/ too


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="CIP_", env_file=(_REPO_ENV, ".env"), extra="ignore"
    )

    catalog: str = "cip"
    schema_raw: str = "raw"
    schema_bronze: str = "bronze"
    schema_silver: str = "silver"
    schema_gold: str = "gold"
    schema_ml: str = "ml"
    schema_serving: str = "serving"
    schema_monitoring: str = "monitoring"
    raw_volume: str = "cofinfad"

    # Used by the gateway; set via CIP_WAREHOUSE_ID (.env locally, ConfigMap on Kubernetes).
    warehouse_id: str | None = None
    # CLI profile for local auth; unset in CI/Kubernetes, where DATABRICKS_* env vars are used.
    databricks_profile: str | None = Field(
        default=None, validation_alias="DATABRICKS_CONFIG_PROFILE"
    )

    serving_endpoint: str = "customer-intelligence"
    model_alias: str = "champion"

    temporal: TemporalDesign = TemporalDesign()
    drift: DriftThresholds = DriftThresholds()

    def table(self, schema: str, name: str) -> str:
        """Fully qualified Unity Catalog name, e.g. table('gold', 'customer_features')."""
        return f"{self.catalog}.{getattr(self, f'schema_{schema}')}.{name}"

    @property
    def raw_volume_path(self) -> str:
        return f"/Volumes/{self.catalog}/{self.schema_raw}/{self.raw_volume}"


@lru_cache
def get_settings() -> Settings:
    return Settings()
