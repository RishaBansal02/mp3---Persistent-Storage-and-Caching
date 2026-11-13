from pathlib import Path


SAMPLE_CSV = (
    Path(__file__).resolve().parents[1] / "fixtures" / "sample_movies.csv"
)


def upload_sample_movies(client):
    with SAMPLE_CSV.open("rb") as csv_file:
        response = client.post(
            "/upload",
            files={"file": (SAMPLE_CSV.name, csv_file, "text/csv")},
        )

    assert response.status_code == 200, response.text
    return response.json()


def test_upload_csv(client):
    result = upload_sample_movies(client)

    assert result == {
        "filename": "sample_movies.csv",
        "rows": 20,
        "columns": 4,
        "column_names": ["title", "release_year", "rating", "genre"],
    }


def test_process_and_retrieve(client):
    upload_sample_movies(client)

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
        {"id", "title", "release_year", "rating", "genre"} == set(movie)
        for movie in result["data"]
    )


def test_get_movies_when_empty(client):
    response = client.get("/movies")

    assert response.status_code == 200, response.text
    assert response.json() == {"data": [], "total_rows": 0}
