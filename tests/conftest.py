import pytest
from fastapi.testclient import TestClient

import main
from src.storage import MovieStorage


@pytest.fixture
def client(tmp_path, monkeypatch):
    test_storage = MovieStorage(tmp_path / "movies.db")
    monkeypatch.setattr(main, "storage", test_storage)

    with TestClient(main.app) as test_client:
        yield test_client
