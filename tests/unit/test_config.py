from datetime import timedelta

import pytest

from cip.config import Settings

T = Settings().temporal


def _splits(prefix: str, horizon_days: int):
    return [
        getattr(T, f"{prefix}_train"),
        getattr(T, f"{prefix}_validation"),
        getattr(T, f"{prefix}_test"),
    ], timedelta(days=horizon_days)


@pytest.mark.parametrize(
    ("prefix", "horizon"),
    [("churn", T.churn_horizon_days), ("value", T.value_horizon_days)],
)
def test_label_windows_close_before_next_split_starts(prefix, horizon):
    """No split may train on outcomes not yet observable at the next split's cutoff."""
    (train, val, test), h = _splits(prefix, horizon)
    assert max(train) + h <= min(val)
    assert max(val) + h <= min(test)


@pytest.mark.parametrize(
    ("prefix", "horizon"),
    [("churn", T.churn_horizon_days), ("value", T.value_horizon_days)],
)
def test_test_labels_are_fully_observed(prefix, horizon):
    (_, _, test), h = _splits(prefix, horizon)
    assert max(test) + h <= T.data_end


def test_feature_lookback_mostly_inside_data():
    """Earliest cutoff may lose at most a few days of lookback to the data start."""
    earliest = min(T.churn_train + T.value_train)
    assert earliest - timedelta(days=T.lookback_days) >= T.data_start - timedelta(days=7)


def test_monitoring_follows_test_period():
    assert max(T.churn_test) < T.monitoring_reference < T.monitoring_current <= T.data_end


def test_qualified_names(monkeypatch):
    monkeypatch.setenv("CIP_CATALOG", "workspace")
    s = Settings()
    assert s.table("gold", "customer_features") == "workspace.gold.customer_features"
    assert s.raw_volume_path == "/Volumes/workspace/raw/cofinfad"
