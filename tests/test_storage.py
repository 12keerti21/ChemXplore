import pandas as pd

from admet_ai.web.app import storage


def test_remove_inactive_users(monkeypatch):
    monkeypatch.setattr(storage, "USER_TO_PREDS", {"old": pd.DataFrame(), "new": pd.DataFrame()})
    monkeypatch.setattr(storage, "USER_TO_LAST_ACTIVITY", {"old": 0.0, "new": 95.0, "no_preds": 0.0})

    assert storage.remove_inactive_users(max_idle_seconds=10, now=100.0) == 2
    assert set(storage.USER_TO_PREDS) == {"new"}
    assert set(storage.USER_TO_LAST_ACTIVITY) == {"new"}


def test_saving_predictions_marks_the_user_active(monkeypatch):
    monkeypatch.setattr(storage, "USER_TO_PREDS", {})
    monkeypatch.setattr(storage, "USER_TO_LAST_ACTIVITY", {})

    storage.set_user_preds("user", pd.DataFrame({"a": [1]}))
    assert "user" in storage.USER_TO_LAST_ACTIVITY
