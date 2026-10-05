"""Shared test setup: API tests never touch the real app database (data/wizard.db) — the read memory
(simplification pass 2) writes there on every live /analysis."""

import pytest


@pytest.fixture(autouse=True)
def _isolated_app_db(monkeypatch, tmp_path):
    import src.api.app as api
    monkeypatch.setattr(api, "_TRADES_DB", str(tmp_path / "app.db"))
