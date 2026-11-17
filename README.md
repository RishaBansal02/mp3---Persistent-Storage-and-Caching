# MP3 Movie API

This FastAPI application stores and queries a collection of movies.
Uploading a CSV replaces the current collection after the API checks the file.
SQLite keeps the movie records available across server restarts.
The processing route validates and cleans the records, then saves the updated collection.
`GET /movies` uses FakeRedis to cache responses for 90 seconds, with a separate entry for each `limit`.
A successful upload or processing request clears the cache so the next request reads the latest records.
`GET /movies/search` queries SQLite directly.

## Run the API and tests

From the MP3 project folder, run these commands:

```bash
source venv/bin/activate
python -m pip install -r requirements.txt
python -m uvicorn main:app --reload --port 8001
```

Open [Swagger UI](http://127.0.0.1:8001/docs). To run the tests, use a second terminal in the same project folder:

```bash
source venv/bin/activate
python -m pytest tests -v
```

## Sample processing request

Upload `fixtures/sample_movies.csv` through `POST /upload`. Then send this JSON to `POST /movies/process`:

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

Expected HTTP 200 response after processing the original sample:

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

Run `GET /movies?limit=100` twice within 90 seconds. Both responses should show `"total_rows": 16`. The server terminal should show a cache miss on the first request and a cache hit on the second.