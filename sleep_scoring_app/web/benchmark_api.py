"""
Benchmark API for comparing data transfer formats.

Run with: uvicorn sleep_scoring_app.web.benchmark_api:app --reload --port 8000
"""

from __future__ import annotations

import csv
import io
import json
import random
import sqlite3
import time
from datetime import datetime, timedelta
from pathlib import Path
from typing import Annotated, Any

from fastapi import FastAPI, Query, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles

app = FastAPI(title="Sleep Scoring Benchmark API")

# CORS for local development
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# Serve static files
static_dir = Path(__file__).parent / "static"
static_dir.mkdir(exist_ok=True)
app.mount("/static", StaticFiles(directory=str(static_dir)), name="static")


# Database path - same as the main app uses
def get_db_path() -> Path:
    """Get the database path."""
    return Path(__file__).parent.parent.parent / "sleep_scoring.db"


def get_db_connection() -> sqlite3.Connection:
    """Get a database connection."""
    db_path = get_db_path()
    if not db_path.exists():
        msg = f"Database not found at {db_path}"
        raise FileNotFoundError(msg)
    return sqlite3.connect(db_path)


def load_real_activity_data(filename: str) -> list[dict[str, Any]]:
    """Load real activity data from the SQLite database for a specific file."""
    conn = get_db_connection()
    conn.row_factory = sqlite3.Row

    query = """
        SELECT timestamp, axis_y, axis_x, axis_z, vector_magnitude
        FROM raw_activity_data
        WHERE filename = ?
        ORDER BY timestamp
    """

    cursor = conn.execute(query, [filename])
    rows = cursor.fetchall()
    conn.close()

    data = []
    for i, row in enumerate(rows):
        data.append(
            {
                "timestamp": row["timestamp"],
                "epoch": i,
                "activity": int(row["vector_magnitude"] or 0),
                "axis_y": int(row["axis_y"] or 0),
                "axis_x": int(row["axis_x"] or 0),
                "axis_z": int(row["axis_z"] or 0),
            }
        )

    return data


def get_available_files() -> list[dict[str, Any]]:
    """Get list of available files in the database."""
    conn = get_db_connection()

    cursor = conn.execute("""
        SELECT filename, COUNT(*) as row_count,
               MIN(timestamp) as start_time,
               MAX(timestamp) as end_time
        FROM raw_activity_data
        GROUP BY filename
        ORDER BY filename
    """)

    files = []
    for row in cursor.fetchall():
        files.append(
            {
                "filename": row[0],
                "row_count": row[1],
                "start_time": row[2],
                "end_time": row[3],
            }
        )

    conn.close()
    return files


def generate_synthetic_data(
    num_rows: int = 20160,
    epoch_seconds: int = 60,
) -> list[dict[str, Any]]:
    """Generate realistic sleep/wake activity data."""
    data = []
    start_time = datetime(2024, 1, 1, 0, 0, 0)

    for i in range(num_rows):
        timestamp = start_time + timedelta(seconds=i * epoch_seconds)
        hour = timestamp.hour

        # Simulate realistic activity pattern
        if hour >= 23 or hour < 6:  # Night - low activity
            base_activity = random.gauss(50, 30)
        elif 6 <= hour < 8:  # Morning wake
            base_activity = random.gauss(300, 100)
        elif 8 <= hour < 22:  # Day - variable
            base_activity = random.gauss(500, 200)
        else:  # Evening wind down
            base_activity = random.gauss(200, 80)

        activity = max(0, int(base_activity))

        data.append(
            {
                "timestamp": timestamp.isoformat(),
                "epoch": i,
                "activity": activity,
                "axis_y": random.randint(0, activity + 50),
                "axis_x": random.randint(0, max(1, activity // 2)),
                "axis_z": random.randint(0, max(1, activity // 3)),
            }
        )

    return data


# Cache for data
_cached_synthetic: list[dict] | None = None
_cached_real: dict[str, list[dict]] = {}

# Default synthetic data size (14 days of minute-by-minute data)
SYNTHETIC_ROWS = 20160


def get_data(
    source: str = "synthetic",
    filename: str | None = None,
) -> list[dict]:
    """Get data from cache or load/generate."""
    global _cached_synthetic

    if source == "real":
        if not filename:
            return []  # Require filename for real data
        if filename not in _cached_real:
            _cached_real[filename] = load_real_activity_data(filename)
        return _cached_real[filename]
    if _cached_synthetic is None:
        _cached_synthetic = generate_synthetic_data(SYNTHETIC_ROWS)
    return _cached_synthetic


@app.get("/")
async def root():
    """Redirect to benchmark page."""
    return HTMLResponse(content='<html><head><meta http-equiv="refresh" content="0; url=/static/benchmark.html"></head></html>')


@app.get("/api/files")
async def list_files():
    """List available files in the database."""
    try:
        files = get_available_files()
        total_rows = sum(f["row_count"] for f in files)
        return {
            "files": files,
            "total_files": len(files),
            "total_rows": total_rows,
        }
    except FileNotFoundError as e:
        return {"error": str(e), "files": [], "total_files": 0, "total_rows": 0}


@app.get("/api/data/json-rows")
async def get_json_rows(
    source: Annotated[str, Query(regex="^(synthetic|real)$")] = "synthetic",
    filename: str | None = None,
):
    """Standard row-based JSON (typical REST response)."""
    start = time.perf_counter()
    data = get_data(source, filename)
    generate_time = time.perf_counter() - start

    start = time.perf_counter()
    content = json.dumps({"data": data, "count": len(data), "source": source})
    serialize_time = time.perf_counter() - start

    return Response(
        content=content,
        media_type="application/json",
        headers={
            "X-Generate-Time-Ms": str(round(generate_time * 1000, 2)),
            "X-Serialize-Time-Ms": str(round(serialize_time * 1000, 2)),
            "X-Row-Count": str(len(data)),
            "X-Data-Source": source,
        },
    )


@app.get("/api/data/json-columnar")
async def get_json_columnar(
    source: Annotated[str, Query(regex="^(synthetic|real)$")] = "synthetic",
    filename: str | None = None,
):
    """Columnar JSON - keys appear once, arrays of values."""
    start = time.perf_counter()
    data = get_data(source, filename)
    generate_time = time.perf_counter() - start

    start = time.perf_counter()
    # Convert row-based to columnar
    if data:
        keys = list(data[0].keys())
        columnar = {key: [row[key] for row in data] for key in keys}
    else:
        columnar = {}
    content = json.dumps({"data": columnar, "count": len(data), "source": source})
    serialize_time = time.perf_counter() - start

    return Response(
        content=content,
        media_type="application/json",
        headers={
            "X-Generate-Time-Ms": str(round(generate_time * 1000, 2)),
            "X-Serialize-Time-Ms": str(round(serialize_time * 1000, 2)),
            "X-Row-Count": str(len(data)),
            "X-Data-Source": source,
        },
    )


@app.get("/api/data/csv")
async def get_csv(
    source: Annotated[str, Query(regex="^(synthetic|real)$")] = "synthetic",
    filename: str | None = None,
):
    """CSV format - compact, easy to parse."""
    start = time.perf_counter()
    data = get_data(source, filename)
    generate_time = time.perf_counter() - start

    start = time.perf_counter()
    output = io.StringIO()
    if data:
        writer = csv.DictWriter(output, fieldnames=data[0].keys())
        writer.writeheader()
        writer.writerows(data)
    content = output.getvalue()
    serialize_time = time.perf_counter() - start

    return Response(
        content=content,
        media_type="text/csv",
        headers={
            "X-Generate-Time-Ms": str(round(generate_time * 1000, 2)),
            "X-Serialize-Time-Ms": str(round(serialize_time * 1000, 2)),
            "X-Row-Count": str(len(data)),
            "X-Data-Source": source,
        },
    )


@app.get("/api/data/msgpack")
async def get_msgpack(
    source: Annotated[str, Query(regex="^(synthetic|real)$")] = "synthetic",
    filename: str | None = None,
):
    """MessagePack - binary JSON alternative."""
    try:
        import msgpack
    except ImportError:
        return Response(
            content=json.dumps({"error": "msgpack not installed. Run: pip install msgpack"}),
            media_type="application/json",
            status_code=501,
        )

    start = time.perf_counter()
    data = get_data(source, filename)
    generate_time = time.perf_counter() - start

    start = time.perf_counter()
    content = msgpack.packb({"data": data, "count": len(data), "source": source})
    serialize_time = time.perf_counter() - start

    return Response(
        content=content,
        media_type="application/msgpack",
        headers={
            "X-Generate-Time-Ms": str(round(generate_time * 1000, 2)),
            "X-Serialize-Time-Ms": str(round(serialize_time * 1000, 2)),
            "X-Row-Count": str(len(data)),
            "X-Data-Source": source,
        },
    )


@app.get("/api/data/arrow")
async def get_arrow(
    source: Annotated[str, Query(regex="^(synthetic|real)$")] = "synthetic",
    filename: str | None = None,
):
    """Apache Arrow IPC format - optimal for DataFrames."""
    try:
        import pyarrow as pa
    except ImportError:
        return Response(
            content=json.dumps({"error": "pyarrow not installed. Run: pip install pyarrow"}),
            media_type="application/json",
            status_code=501,
        )

    start = time.perf_counter()
    data = get_data(source, filename)
    generate_time = time.perf_counter() - start

    start = time.perf_counter()
    if data:
        keys = list(data[0].keys())
        arrays = {}
        for key in keys:
            values = [row[key] for row in data]
            if key in {"timestamp", "filename"}:
                arrays[key] = pa.array(values)
            else:
                arrays[key] = pa.array(values, type=pa.int32())
        table = pa.table(arrays)

        sink = pa.BufferOutputStream()
        with pa.ipc.RecordBatchStreamWriter(sink, table.schema) as writer:
            writer.write_table(table)
        content = sink.getvalue().to_pybytes()
    else:
        content = b""
    serialize_time = time.perf_counter() - start

    return Response(
        content=content,
        media_type="application/vnd.apache.arrow.stream",
        headers={
            "X-Generate-Time-Ms": str(round(generate_time * 1000, 2)),
            "X-Serialize-Time-Ms": str(round(serialize_time * 1000, 2)),
            "X-Row-Count": str(len(data)),
            "X-Data-Source": source,
        },
    )


@app.get("/api/formats")
async def list_formats():
    """List available data formats with descriptions."""
    return {
        "formats": [
            {
                "id": "json-rows",
                "name": "JSON (Row-based)",
                "description": "Standard REST response format",
                "endpoint": "/api/data/json-rows",
            },
            {
                "id": "json-columnar",
                "name": "JSON (Columnar)",
                "description": "Keys appear once, arrays of values",
                "endpoint": "/api/data/json-columnar",
            },
            {
                "id": "csv",
                "name": "CSV",
                "description": "Comma-separated values",
                "endpoint": "/api/data/csv",
            },
            {
                "id": "msgpack",
                "name": "MessagePack",
                "description": "Binary JSON alternative",
                "endpoint": "/api/data/msgpack",
            },
            {
                "id": "arrow",
                "name": "Apache Arrow",
                "description": "Columnar binary format",
                "endpoint": "/api/data/arrow",
            },
        ]
    }


@app.get("/api/stats")
async def get_stats():
    """Get database statistics."""
    try:
        conn = get_db_connection()
        cursor = conn.execute("SELECT COUNT(*) FROM raw_activity_data")
        total_rows = cursor.fetchone()[0]

        cursor = conn.execute("SELECT COUNT(DISTINCT filename) FROM raw_activity_data")
        total_files = cursor.fetchone()[0]

        conn.close()

        return {
            "total_rows": total_rows,
            "total_files": total_files,
            "database_path": str(get_db_path()),
        }
    except FileNotFoundError as e:
        return {"error": str(e), "total_rows": 0, "total_files": 0}


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8000)  # noqa: S104
