"""
Background processor for TUS-uploaded files.

Handles decompression, format detection, chunked processing for raw GENEActiv
files, and standard loading for epoch/ActiGraph files.
"""

from __future__ import annotations

import asyncio
import functools
import gzip
import logging
import shutil
import tempfile
from pathlib import Path

from sqlalchemy import delete, select

from sleep_scoring_web.db.models import File as FileModel
from sleep_scoring_web.db.models import RawActivityData
from sleep_scoring_web.db.session import async_session_maker
from sleep_scoring_web.schemas.enums import FileStatus
from sleep_scoring_web.services.loaders.csv_loader import CSVLoaderService
from sleep_scoring_web.services.loaders.geneactiv_processor import is_raw_geneactiv, process_raw_geneactiv
from sleep_scoring_web.services.processing_tracker import clear_tracking, start_tracking, update_progress

logger = logging.getLogger(__name__)

# Streaming decompression buffer size (512KB — larger buffers reduce syscalls for multi-GB files)
DECOMPRESS_BUFFER_SIZE = 524288


async def process_uploaded_file(
    file_id: int,
    tus_file_path: str,
    original_filename: str,
    is_gzip: bool,
    username: str,
    skip_rows: int = 10,
    device_preset: str | None = None,
) -> None:
    """
    Process a TUS-uploaded file in the background.

    1. Decompress if gzipped (streaming, never loads full file)
    2. Detect file type
    3. Process: raw GENEActiv → chunked agcounts, or epoch → CSVLoaderService
    4. Insert epoch data into database
    5. Update FileModel status
    """
    progress = start_tracking(file_id)
    csv_path = Path(tus_file_path)
    temp_decompressed: Path | None = None

    loop = asyncio.get_running_loop()

    try:
        async with async_session_maker() as db:
            # Update status to PROCESSING
            result = await db.execute(select(FileModel).where(FileModel.id == file_id))
            file_model = result.scalar_one_or_none()
            if file_model is None:
                logger.error("File %d not found in database", file_id)
                update_progress(file_id, status=FileStatus.FAILED, error="File record not found")
                return
            file_model.status = FileStatus.PROCESSING
            await db.commit()

            # Step 1: Decompress if gzipped
            if is_gzip:
                update_progress(file_id, phase="decompressing", percent=5.0)
                tmp = tempfile.NamedTemporaryFile(suffix=".csv", delete=False)
                tmp.close()
                temp_decompressed = Path(tmp.name)
                await loop.run_in_executor(None, _streaming_decompress, csv_path, temp_decompressed)
                csv_path = temp_decompressed
                update_progress(file_id, phase="decompressing", percent=15.0)

            # Step 2: Validate CSV format (read first 5 lines)
            await loop.run_in_executor(None, _validate_csv_format, csv_path)

            # Step 3: Detect file type and process
            from sleep_scoring_web.api.files import bulk_insert_activity_data

            if is_raw_geneactiv(csv_path):
                # Raw GENEActiv: chunked processing with agcounts.
                # Creates a SEPARATE epoch file record — the raw file is kept as-is.
                update_progress(file_id, phase="converting_counts", percent=20.0)

                def on_progress(phase: str, pct: float, rows: int) -> None:
                    scaled = 20.0 + (pct / 100.0) * 70.0
                    update_progress(file_id, phase=phase, percent=scaled, rows_processed=rows)

                result_info = await loop.run_in_executor(
                    None,
                    functools.partial(
                        process_raw_geneactiv,
                        file_path=csv_path,
                        file_id=file_id,
                        progress_callback=on_progress,
                    ),
                )

                # Build epoch filename: strip extension, add _60sec.csv
                raw_name = original_filename
                stem = raw_name.rsplit(".", 1)[0] if "." in raw_name else raw_name
                epoch_filename = f"{stem}_60sec.csv"

                # Check if epoch file already exists (re-upload)
                existing_epoch = await db.execute(
                    select(FileModel).where(FileModel.filename == epoch_filename)
                )
                epoch_model = existing_epoch.scalar_one_or_none()
                if epoch_model:
                    # Clear old activity data for re-processing
                    await db.execute(delete(RawActivityData).where(RawActivityData.file_id == epoch_model.id))
                else:
                    # Create new epoch file record
                    epoch_model = FileModel(
                        filename=epoch_filename,
                        original_path=str(csv_path),
                        file_type="csv",
                        participant_id=file_model.participant_id,
                        status=FileStatus.PROCESSING,
                        uploaded_by=username,
                    )
                    db.add(epoch_model)
                    await db.flush()  # Get epoch_model.id

                # Insert epoch data into the NEW file record
                update_progress(file_id, phase="inserting_db", percent=90.0)
                total_inserted = 0
                for epoch_df in result_info["epoch_dfs"]:
                    n = await bulk_insert_activity_data(db, epoch_model.id, epoch_df)
                    total_inserted += n

                # Update epoch file record
                epoch_model.status = FileStatus.READY
                epoch_model.row_count = total_inserted
                if result_info["start_time"] is not None:
                    epoch_model.start_time = result_info["start_time"]
                if result_info["end_time"] is not None:
                    epoch_model.end_time = result_info["end_time"]
                epoch_model.metadata_json = {
                    "loader": "geneactiv_raw_agcounts",
                    "sample_rate": result_info["sample_rate"],
                    "source_file_id": file_id,
                    "epoch_length_seconds": 60,
                }

                # Mark the raw file as processed (not scorable)
                file_model.status = FileStatus.RAW
                file_model.metadata_json = {
                    "type": "raw_geneactiv",
                    "sample_rate": result_info["sample_rate"],
                    "epoch_file_id": epoch_model.id,
                    "epoch_filename": epoch_filename,
                }

            else:
                # Epoch-compressed GENEActiv or ActiGraph: use standard loader
                update_progress(file_id, phase="reading_csv", percent=30.0)
                loader = CSVLoaderService(skip_rows=skip_rows, device_preset=device_preset)
                loaded = await loop.run_in_executor(None, loader.load_file, csv_path)

                update_progress(file_id, phase="inserting_db", percent=70.0)
                activity_df = loaded["activity_data"]
                metadata = loaded["metadata"]

                total_inserted = await bulk_insert_activity_data(db, file_id, activity_df)

                file_model.status = FileStatus.READY
                file_model.row_count = total_inserted
                if "start_time" in metadata and metadata["start_time"] is not None:
                    file_model.start_time = metadata["start_time"]
                if "end_time" in metadata and metadata["end_time"] is not None:
                    file_model.end_time = metadata["end_time"]
                file_model.metadata_json = {
                    "loader": metadata.get("loader", "csv"),
                    "device_type": metadata.get("device_type"),
                    "epoch_length_seconds": metadata.get("epoch_length_seconds", 60),
                }

            update_progress(file_id, phase="inserting_db", percent=100.0, status=FileStatus.READY)
            await db.commit()
            logger.info(
                "File %d (%s) processed: %d epochs inserted",
                file_id,
                original_filename,
                total_inserted,
            )

    except Exception as exc:
        logger.exception("Failed to process file %d (%s)", file_id, original_filename)
        error_msg = str(exc)
        update_progress(file_id, status=FileStatus.FAILED, error=error_msg)

        # Cleanup partial data and mark as failed
        try:
            async with async_session_maker() as db:
                # Delete any partial activity data
                await db.execute(delete(RawActivityData).where(RawActivityData.file_id == file_id))
                # Update file status
                result = await db.execute(select(FileModel).where(FileModel.id == file_id))
                file_model = result.scalar_one_or_none()
                if file_model:
                    file_model.status = FileStatus.FAILED
                    file_model.metadata_json = {"error": error_msg}
                await db.commit()
        except Exception:
            logger.exception("Failed to cleanup after processing error for file %d", file_id)

    finally:
        # Cleanup temp decompressed file
        if temp_decompressed and temp_decompressed.exists():
            temp_decompressed.unlink(missing_ok=True)
        # Keep tracking for a while so frontend can poll final status
        # (cleared by lifespan cleanup or next upload)


def _streaming_decompress(gz_path: Path, out_path: Path) -> None:
    """Decompress a gzip file using streaming (never loads full file into memory)."""
    with gzip.open(gz_path, "rb") as f_in, open(out_path, "wb") as f_out:
        shutil.copyfileobj(f_in, f_out, length=DECOMPRESS_BUFFER_SIZE)


def _validate_csv_format(csv_path: Path) -> None:
    """Read first few lines to validate the file looks like a CSV."""
    with open(csv_path, encoding="utf-8", errors="ignore") as f:
        lines = []
        for i, line in enumerate(f):
            lines.append(line)
            if i >= 5:
                break

    if not lines:
        msg = "Empty file"
        raise ValueError(msg)

    # Check that at least one line has commas or tabs (delimiter)
    has_delimiter = any("," in line or "\t" in line for line in lines)
    if not has_delimiter:
        msg = "File does not appear to be CSV (no commas or tabs found)"
        raise ValueError(msg)
