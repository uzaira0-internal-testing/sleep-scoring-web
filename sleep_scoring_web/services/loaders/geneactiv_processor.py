"""Chunked GENEActiv raw data processor with agcounts conversion.

Processes multi-GB raw GENEActiv CSV files (100Hz, 7 columns) in chunks,
converting raw accelerometer data to 60-second epoch activity counts using
the agcounts library. Memory usage stays ~10MB per chunk regardless of file size.
"""

from __future__ import annotations

import logging
import re
from collections.abc import Callable
from pathlib import Path

import numpy as np
import pandas as pd
from agcounts.extract import get_counts

from .csv_loader import CSVLoaderService

logger = logging.getLogger(__name__)

# 1 minute of 100Hz data = 6000 samples. Process 10 minutes at a time.
CHUNK_SIZE = 600_000  # ~10 minutes of 100Hz data per chunk (~10MB RAM)
EPOCH_SECONDS = 60


def process_raw_geneactiv(
    file_path: Path,
    file_id: int,
    db_session,
    insert_fn: Callable,
    progress_callback: Callable[[str, float, int], None] | None = None,
) -> dict:
    """Process a raw GENEActiv CSV file in chunks, converting to epoch counts.

    Args:
        file_path: Path to the raw GENEActiv CSV file
        file_id: Database file ID for inserted rows
        db_session: Async database session
        insert_fn: Async function(db, file_id, df) -> int for bulk inserting
        progress_callback: Optional callback(phase, percent, rows_processed)

    Returns:
        dict with total_epochs, start_time, end_time, sample_rate
    """
    # Parse header to find data start and measurement frequency
    data_start, has_header = CSVLoaderService._find_geneactiv_data_start(file_path)
    freq = _detect_frequency(file_path)

    # Detect delimiter
    with open(file_path, encoding="utf-8", errors="ignore") as f:
        for i, line in enumerate(f):
            if i == data_start:
                sep = "\t" if "\t" in line else ","
                break
        else:
            sep = ","

    # Estimate total rows for progress reporting
    total_rows_estimate = _estimate_total_rows(file_path, data_start)
    samples_per_epoch = freq * EPOCH_SECONDS

    if progress_callback:
        progress_callback("reading_csv", 0.0, 0)

    # Set up column names for headerless reading
    col_names = ["timestamp", "x", "y", "z", "lux", "button", "temperature"]

    # Read CSV in chunks — single reader creation
    if has_header:
        reader = pd.read_csv(
            file_path,
            skiprows=data_start - 1,
            header=0,
            sep=sep,
            skipinitialspace=True,
            chunksize=CHUNK_SIZE,
            usecols=lambda c: c.lower().strip() in ("timestamp", "x", "y", "z"),
        )
    else:
        reader = pd.read_csv(
            file_path,
            skiprows=data_start,
            header=None,
            names=col_names,
            sep=sep,
            skipinitialspace=True,
            chunksize=CHUNK_SIZE,
            usecols=[0, 1, 2, 3],  # timestamp, x, y, z
        )

    # Rolling buffer for partial-epoch samples at chunk boundaries
    leftover_samples: np.ndarray | None = None
    leftover_timestamps: list = []

    total_epochs_inserted = 0
    total_rows_read = 0
    first_timestamp = None
    last_timestamp = None
    all_epoch_dfs: list[pd.DataFrame] = []

    for chunk_df in reader:
        total_rows_read += len(chunk_df)

        # Normalize column names
        chunk_df.columns = [c.lower().strip() for c in chunk_df.columns]

        # Fix GENEActiv colon-millisecond timestamps
        ts_col = "timestamp" if "timestamp" in chunk_df.columns else chunk_df.columns[0]
        if chunk_df[ts_col].dtype == object:
            chunk_df[ts_col] = chunk_df[ts_col].str.replace(
                r":(\d{3})$", r".\1", regex=True
            )
        chunk_df[ts_col] = pd.to_datetime(chunk_df[ts_col])

        if first_timestamp is None:
            first_timestamp = chunk_df[ts_col].iloc[0]
        last_timestamp = chunk_df[ts_col].iloc[-1]

        # Extract x, y, z as numpy array
        xyz_cols = ["x", "y", "z"]
        xyz = chunk_df[xyz_cols].to_numpy(dtype=np.float64)
        timestamps = chunk_df[ts_col].tolist()

        # Prepend leftover from previous chunk
        if leftover_samples is not None and len(leftover_samples) > 0:
            xyz = np.vstack([leftover_samples, xyz])
            timestamps = leftover_timestamps + timestamps

        # Calculate how many complete epochs we have
        n_complete_samples = (len(xyz) // samples_per_epoch) * samples_per_epoch

        if n_complete_samples == 0:
            # Not enough for a full epoch yet — save everything as leftover
            leftover_samples = xyz
            leftover_timestamps = timestamps
            continue

        # Save leftover for next chunk
        if len(xyz) > n_complete_samples:
            leftover_samples = xyz[n_complete_samples:]
            leftover_timestamps = timestamps[n_complete_samples:]
        else:
            leftover_samples = None
            leftover_timestamps = []

        # Process complete samples through agcounts
        complete_xyz = xyz[:n_complete_samples]
        epoch_counts = get_counts(complete_xyz, freq=freq, epoch=EPOCH_SECONDS)

        # Build epoch timestamps (start of each epoch)
        epoch_timestamps = []
        for ei in range(len(epoch_counts)):
            idx = ei * samples_per_epoch
            if idx < len(timestamps):
                epoch_timestamps.append(timestamps[idx])
            else:
                # Extrapolate from last known timestamp
                epoch_timestamps.append(
                    timestamps[-1] + pd.Timedelta(seconds=EPOCH_SECONDS * (ei - len(epoch_counts) + 1))
                )

        # Create epoch DataFrame matching the database schema
        epoch_df = pd.DataFrame(
            {
                "timestamp": epoch_timestamps[: len(epoch_counts)],
                "axis_x": epoch_counts[:, 0] if epoch_counts.shape[1] > 0 else 0,
                "axis_y": epoch_counts[:, 1] if epoch_counts.shape[1] > 1 else 0,
                "axis_z": epoch_counts[:, 2] if epoch_counts.shape[1] > 2 else 0,
            }
        )
        # Calculate vector magnitude from counts
        epoch_df["vector_magnitude"] = np.sqrt(
            epoch_df["axis_x"] ** 2 + epoch_df["axis_y"] ** 2 + epoch_df["axis_z"] ** 2
        )

        all_epoch_dfs.append(epoch_df)
        total_epochs_inserted += len(epoch_df)

        if progress_callback:
            pct = min(95.0, (total_rows_read / max(total_rows_estimate, 1)) * 100)
            progress_callback("converting_counts", pct, total_epochs_inserted)

    # Process any remaining leftover samples (final partial epoch)
    if leftover_samples is not None and len(leftover_samples) >= samples_per_epoch:
        n_complete = (len(leftover_samples) // samples_per_epoch) * samples_per_epoch
        complete_xyz = leftover_samples[:n_complete]
        epoch_counts = get_counts(complete_xyz, freq=freq, epoch=EPOCH_SECONDS)

        epoch_timestamps = []
        for ei in range(len(epoch_counts)):
            idx = ei * samples_per_epoch
            if idx < len(leftover_timestamps):
                epoch_timestamps.append(leftover_timestamps[idx])
            else:
                epoch_timestamps.append(
                    leftover_timestamps[-1] + pd.Timedelta(seconds=EPOCH_SECONDS)
                )

        epoch_df = pd.DataFrame(
            {
                "timestamp": epoch_timestamps[: len(epoch_counts)],
                "axis_x": epoch_counts[:, 0] if epoch_counts.shape[1] > 0 else 0,
                "axis_y": epoch_counts[:, 1] if epoch_counts.shape[1] > 1 else 0,
                "axis_z": epoch_counts[:, 2] if epoch_counts.shape[1] > 2 else 0,
            }
        )
        epoch_df["vector_magnitude"] = np.sqrt(
            epoch_df["axis_x"] ** 2 + epoch_df["axis_y"] ** 2 + epoch_df["axis_z"] ** 2
        )
        all_epoch_dfs.append(epoch_df)
        total_epochs_inserted += len(epoch_df)

    return {
        "total_epochs": total_epochs_inserted,
        "start_time": first_timestamp,
        "end_time": last_timestamp,
        "sample_rate": freq,
        "epoch_dfs": all_epoch_dfs,
    }


def _detect_frequency(file_path: Path) -> int:
    """Detect measurement frequency from GENEActiv header.

    Looks for lines like 'Measurement Frequency,100 Hz' in the header.
    Defaults to 100 Hz if not found.
    """
    freq_pattern = re.compile(r"(?:measurement\s*frequency|sample\s*rate)[,:\t]\s*(\d+)", re.IGNORECASE)
    with open(file_path, encoding="utf-8", errors="ignore") as f:
        for i, line in enumerate(f):
            if i > 120:
                break
            m = freq_pattern.search(line)
            if m:
                return int(m.group(1))
    return 100  # Default GENEActiv frequency


def _estimate_total_rows(file_path: Path, data_start: int) -> int:
    """Estimate total data rows from file size and sample line length."""
    file_size = file_path.stat().st_size
    # Read a sample data line to estimate average line length
    with open(file_path, encoding="utf-8", errors="ignore") as f:
        for i, line in enumerate(f):
            if i == data_start:
                avg_line_len = len(line.encode("utf-8"))
                break
        else:
            avg_line_len = 80

    if avg_line_len == 0:
        avg_line_len = 80
    return max(1, file_size // avg_line_len)


def is_raw_geneactiv(file_path: Path) -> bool:
    """Check if a GENEActiv file is raw (100Hz, 7 cols) vs epoch-compressed."""
    if not CSVLoaderService.detect_geneactiv(file_path):
        return False

    data_start, has_header = CSVLoaderService._find_geneactiv_data_start(file_path)

    with open(file_path, encoding="utf-8", errors="ignore") as f:
        for i, line in enumerate(f):
            if i == data_start:
                sep = "\t" if "\t" in line else ","
                num_cols = len(line.strip().split(sep))
                return num_cols <= 7  # Raw = 7 cols, epoch = 12 cols

    return False
