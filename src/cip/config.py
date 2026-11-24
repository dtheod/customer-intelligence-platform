"""Central configuration. Override any field with a CIP_-prefixed env var (e.g. CIP_CATALOG)."""

from datetime import date
from functools import lru_cache

from pydantic import BaseModel
from pydantic_settings import BaseSettings, SettingsConfigDict


class TemporalDesign(BaseModel):
    """Month-end cutoffs and windows. See docs/PLAN.md section 0."""

    lookback_days: int = 90
    active_window_days: int = 90
    churn_horizon_days: int = 30
    value_horizon_days: int = 90

    churn_train: list[date] = [
        date(2023, 4, 30),
        date(2023, 5, 31),
        date(2023, 6, 30),
        date(2023, 7, 31),
    ]
    churn_validation: list[date] = [date(2023, 8, 31)]
    churn_test: list[date] = [date(2023, 9, 30)]
    monitoring_reference: date = date(2023, 10, 31)
    monitoring_current: date = date(2023, 11, 30)


class DriftThresholds(BaseModel):
    psi_warning: float = 0.10
    psi_retrain: float = 0.25


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="CIP_", env_file=".env", extra="ignore")

    catalog: str = "cip"
    schema_raw: str = "raw"
    schema_bronze: str = "bronze"
    schema_silver: str = "silver"
    schema_gold: str = "gold"
    schema_ml: str = "ml"
    schema_serving: str = "serving"
    schema_monitoring: str = "monitoring"
    raw_volume: str = "cofinfad"

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
