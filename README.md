# MP3 Movie API

This FastAPI application stores and queries a single collection of movies.
The upload route validates the CSV layout before replacing the collection.
The storage and database modules use SQLite to keep the movie rows across server restarts and to filter, sort, and count them with SQL.
The processing route uses the data pipeline to validate and clean the rows, then writes the cleaned collection back to SQLite.
Repeated requests to GET /movies reuse a FakeRedis response for up to 90 seconds, with a separate entry for each limit.
Successful uploads and processing clear those entries so the next retrieval uses the updated collection.
Movie search queries SQLite directly.

## Run the API and tests

From the repository root with the virtual environment active:

```bash
python -m pip install -r requirements.txt
python -m uvicorn main:app --reload
```

Open [Swagger UI](http://127.0.0.1:8000/docs). In a second terminal with the same environment active, run:

```bash
python -m pytest tests -v
```

## Sample processing request

Upload `fixtures/sample_movies.csv` to `POST /upload`, then use this JSON body for `POST /movies/process`:

```json
{
  "validation": {
    "required_columns": ["title", "release_year", "rating", "genre"],
    "numeric_columns": ["release_year", "rating"]
  },
  "processing": {
    "remove_duplicates": true,
    "missing": {"enabled": true, "axis": "rows"},
    "outliers": {
      "enabled": true,
      "columns": ["rating"],
      "method": "iqr",
      "threshold": 1.5
    }
  }
}
```

Expected HTTP 200 response for the original sample:

```json
{
  "validation_rows_removed": 0,
  "cleaning_report": {
    "rows_before": 20,
    "rows_after": 16,
    "rows_removed": 4,
    "columns_before": 4,
    "columns_after": 4,
    "columns_removed": 0
  }
}
```

Call `GET /movies?limit=100` twice. The first call after processing shows a cache miss and returns 16 movies. The second call shows a cache hit.
