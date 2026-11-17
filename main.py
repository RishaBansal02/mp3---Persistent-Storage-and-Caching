import io
import logging
from pathlib import Path
from threading import Lock

import pandas as pd
from fastapi import FastAPI, File, HTTPException, Query, UploadFile

from data_pipeline import (
    create_cleaning_report,
    process_data,
    validate_dataframe,
)
from src import (
    HealthResponse,
    MovieCache,
    MovieDataResponse,
    MovieProcessingReport,
    MovieStorage,
    MovieUploadInfo,
    ProcessConfig,
    log_requests,
    setup_logging,
)
from src.storage import MOVIE_COLUMNS


setup_logging(verbose=True)
logger = logging.getLogger(__name__)

app = FastAPI(title="Data Processing API", version="1.0.0")
app.middleware("http")(log_requests)

storage = MovieStorage()
cache = MovieCache()
movie_cache_lock = Lock()


@app.get("/health", response_model=HealthResponse)
def health_check():
    """Return the application status and version."""
    return {"status": "ok", "version": "1.0.0"}


@app.post("/upload", response_model=MovieUploadInfo)
async def upload_movies(file: UploadFile = File(...)):
    """Read a movie CSV and replace the stored collection."""
    filename = file.filename or ""
    extension = Path(filename).suffix.lower()

    if extension != ".csv":
        logger.warning("Unsupported file format: %s", extension)
        raise HTTPException(
            status_code=400,
            detail="Only CSV files are supported",
        )

    try:
        contents = await file.read()
        df = pd.read_csv(io.BytesIO(contents))
    except (
        pd.errors.EmptyDataError,
        pd.errors.ParserError,
        UnicodeDecodeError,
    ) as error:
        logger.warning("Invalid CSV file: %s", error)
        raise HTTPException(
            status_code=400,
            detail="Unable to read CSV file",
        ) from error

    if sorted(df.columns) != sorted(MOVIE_COLUMNS):
        raise HTTPException(
            status_code=400,
            detail="CSV must contain exactly title, release_year, rating, and genre",
        )

    if df.empty:
        raise HTTPException(
            status_code=400,
            detail="CSV must contain at least one movie",
        )

    df = df[MOVIE_COLUMNS]

    with movie_cache_lock:
        storage.save(df)
        cache.invalidate()

    logger.info("Uploaded movies: filename=%s, rows=%s", filename, len(df))

    return MovieUploadInfo(
        filename=filename,
        rows=len(df),
        columns=len(df.columns),
        column_names=df.columns.tolist(),
    )


@app.get("/movies", response_model=MovieDataResponse)
def get_movies(limit: int = Query(default=100, ge=1)):
    """Return up to limit movies and the total collection size."""
    with movie_cache_lock:
        cached = cache.get(limit)
        if cached is not None:
            return cached

        records = storage.select_columns(MOVIE_COLUMNS, limit)
        total_rows = storage.count_movies()
        response = MovieDataResponse(data=records, total_rows=total_rows)
        cache.set(limit, response.model_dump())

    logger.info(
        "Retrieved movies: returned_rows=%s, total_rows=%s",
        len(records),
        total_rows,
    )

    return response


@app.get("/movies/search", response_model=list[dict])
def search_movies(
    columns: list[str] = Query(default=["title"]),
    min_rating: float = Query(default=0, ge=0, le=10),
    limit: int = Query(default=100, ge=1),
):
    """Return the requested fields for movies that meet the minimum rating."""
    try:
        records = storage.query_movies(columns, min_rating, limit)
    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error

    logger.info(
        "Queried movies: columns=%s, min_rating=%s, returned_rows=%s",
        columns,
        min_rating,
        len(records),
    )

    return records


@app.post("/movies/process", response_model=MovieProcessingReport)
def process_movies(config: ProcessConfig):
    """Validate, clean, and save the current movie collection."""
    with movie_cache_lock:
        df = storage.get()

        if df.empty:
            raise HTTPException(
                status_code=400,
                detail="No movies to process. Upload a movie CSV first.",
            )

        config_dict = config.model_dump()

        try:
            required_columns = config.validation.required_columns
            numeric_columns = config.validation.numeric_columns

            for column in numeric_columns:
                if column not in df.columns:
                    raise ValueError(f"Numeric column not found: {column}")

            validated_df = validate_dataframe(df, required_columns, numeric_columns)
            validation_rows_removed = len(df) - len(validated_df)
            validated_copy = validated_df.copy()

            processed_df = process_data(validated_df, config_dict)
            cleaning_report = create_cleaning_report(validated_copy, processed_df)

            missing_columns = [
                column for column in MOVIE_COLUMNS if column not in processed_df.columns
            ]
            if missing_columns:
                raise ValueError(
                    f"Processing removed required movie columns: {', '.join(missing_columns)}"
                )

        except ValueError as error:
            logger.warning("Movie processing failed: %s", error)
            raise HTTPException(status_code=400, detail=str(error)) from error

        storage.save(processed_df)
        cache.invalidate()

    logger.info(
        "Processed movies: validation_removed=%s, rows_before=%s, rows_after=%s",
        validation_rows_removed,
        len(validated_copy),
        len(processed_df),
    )

    return MovieProcessingReport(
        validation_rows_removed=validation_rows_removed,
        cleaning_report=cleaning_report,
    )
