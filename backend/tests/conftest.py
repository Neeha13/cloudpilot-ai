import os

import pytest
from fastapi.testclient import TestClient


@pytest.fixture()
def client(tmp_path, monkeypatch):
    # Each test gets its own SQLite file so tests never touch the developer's cloudpilot.db.
    monkeypatch.setenv("DATABASE_PATH", str(tmp_path / "test.db"))
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    from app.main import app
    from app import snapshots
    snapshots.clear_cache()
    with TestClient(app) as c:
        yield c
