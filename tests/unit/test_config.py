from datetime import timedelta

from cip.config import Settings


def test_splits_are_strictly_ordered_and_disjoint():
    t = Settings().temporal
    ordered = [
        *t.churn_train,
        *t.churn_validation,
        *t.churn_test,
        t.monitoring_reference,
        t.monitoring_current,
    ]
    assert ordered == sorted(ordered)
    assert len(ordered) == len(set(ordered))


def test_training_label_windows_end_before_test_cutoff():
    """No training label window may overlap the test period."""
    t = Settings().temporal
    horizon = timedelta(days=t.churn_horizon_days)
    assert max(t.churn_train) + horizon <= t.churn_test[0]


def test_qualified_names(monkeypatch):
    monkeypatch.setenv("CIP_CATALOG", "workspace")
    s = Settings()
    assert s.table("gold", "customer_features") == "workspace.gold.customer_features"
    assert s.raw_volume_path == "/Volumes/workspace/raw/cofinfad"
