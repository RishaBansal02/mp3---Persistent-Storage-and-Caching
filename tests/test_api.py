import csv
from io import StringIO

import pytest

import main
from src import MovieStorage


def test_upload_csv(uploaded_movies):
    assert uploaded_movies == {
        "filename": "sample_movies.csv",
        "rows": 20,
        "columns": 4,
        "column_names": ["title", "release_year", "rating", "genre"],
    }


def test_process_and_retrieve(client, uploaded_movies):
    config = {
        "validation": {
            "required_columns": ["title", "release_year", "rating", "genre"],
            "numeric_columns": ["release_year", "rating"],
        },
        "processing": {},
    }

    response = client.post("/movies/process", json=config)
    assert response.status_code == 200, response.text
    report = response.json()
    assert isinstance(report["validation_rows_removed"], int)
    assert isinstance(report["cleaning_report"], dict)

    response = client.get("/movies", params={"limit": 2})
    assert response.status_code == 200, response.text
    result = response.json()
    assert len(result["data"]) == 2
    assert result["total_rows"] >= 2
    assert all(
        set(movie) == {"id", "title", "release_year", "rating", "genre"}
        for movie in result["data"]
    )


def test_get_movies_when_empty(client):
    response = client.get("/movies")

    assert response.status_code == 200, response.text
    assert response.json() == {"data": [], "total_rows": 0}


def test_movies_persist(client, test_storage, uploaded_movies, sample_csv_bytes):
    reopened = MovieStorage(test_storage.db_path)
    movies = reopened.get()

    with StringIO(sample_csv_bytes.decode("utf-8")) as sample:
        titles = [row["title"] for row in csv.DictReader(sample)]

    assert reopened.count_movies() == len(movies) == 20
    assert list(movies.columns) == ["title", "release_year", "rating", "genre"]
    assert movies["title"].tolist() == titles

    response = client.get("/movies", params={"limit": 100})
    assert response.status_code == 200, response.text
    expected_ids = list(range(1, 21))
    saved_rows = reopened.select_columns(["title"], 100)
    assert [row["id"] for row in saved_rows] == expected_ids
    assert [row["id"] for row in response.json()["data"]] == expected_ids


def test_cache_and_processing(client, uploaded_movies, processing_body):
    for limit in (100, 1):
        response = client.get("/movies", params={"limit": limit})
        assert response.status_code == 200, response.text
        assert main.cache.get(limit) == response.json()

    processed = client.post("/movies/process", json=processing_body)
    assert processed.status_code == 200, processed.text
    assert processed.json() == {
        "validation_rows_removed": 0,
        "cleaning_report": {
            "rows_before": 20,
            "rows_after": 16,
            "rows_removed": 4,
            "columns_before": 4,
            "columns_after": 4,
            "columns_removed": 0,
        },
    }
    assert main.cache.get(100) is None
    assert main.cache.get(1) is None

    updated = client.get("/movies", params={"limit": 100})
    assert updated.status_code == 200, updated.text
    result = updated.json()
    assert result["total_rows"] == 16
    assert [row["title"] for row in result["data"]] == [
        f"Movie {letter}" for letter in "ABCDEFGHIJKLMNOP"
    ]
    assert [row["id"] for row in result["data"]] == list(range(1, 17))
    assert main.cache.get(100) == result


def test_cache_hit_skips_database(client, uploaded_movies, monkeypatch):
    first = client.get("/movies", params={"limit": 100})
    assert first.status_code == 200, first.text

    def unexpected_database_read(*args, **kwargs):
        pytest.fail("Cache hit queried SQLite")

    monkeypatch.setattr(main.storage, "select_columns", unexpected_database_read)
    monkeypatch.setattr(main.storage, "count_movies", unexpected_database_read)

    repeated = client.get("/movies", params={"limit": 100})
    assert repeated.status_code == 200, repeated.text
    assert repeated.json() == first.json()
