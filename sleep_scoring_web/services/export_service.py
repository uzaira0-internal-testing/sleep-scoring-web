"""
Export service for sleep scoring data.

Generates CSV exports with selectable columns from markers and metrics data.
"""

from __future__ import annotations

import csv
import io
import logging
from dataclasses import dataclass, field
from datetime import UTC, date, datetime, timezone
from typing import TYPE_CHECKING, Any

from sqlalchemy import and_, select

from sleep_scoring_web.db.models import File, Marker, SleepMetric, UserAnnotation
from sleep_scoring_web.schemas.enums import (
    AlgorithmType,
    MarkerCategory,
    MarkerType,
    SleepPeriodDetectorType,
    VerificationStatus,
)

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)

# Value display formatting for standardized capitalization
_MARKER_TYPE_DISPLAY = {
    MarkerType.MAIN_SLEEP: "Main Sleep",
    MarkerType.NAP: "Nap",
    MarkerType.MANUAL_NONWEAR: "Manual Nonwear",
}

_ALGORITHM_DISPLAY = {
    AlgorithmType.SADEH_1994_ACTILIFE: "Sadeh 1994 (ActiLife)",
    AlgorithmType.SADEH_1994_ORIGINAL: "Sadeh 1994 (Original)",
    AlgorithmType.COLE_KRIPKE_1992_ACTILIFE: "Cole-Kripke 1992 (ActiLife)",
    AlgorithmType.COLE_KRIPKE_1992_ORIGINAL: "Cole-Kripke 1992 (Original)",
    AlgorithmType.MANUAL: "Manual",
}

_DETECTION_RULE_DISPLAY = {
    SleepPeriodDetectorType.CONSECUTIVE_ONSET3S_OFFSET5S: "3 Epochs / 5 Min",
    SleepPeriodDetectorType.CONSECUTIVE_ONSET5S_OFFSET10S: "5 Epochs / 10 Min",
    SleepPeriodDetectorType.TUDOR_LOCKE_2014: "Tudor-Locke 2014",
}

_VERIFICATION_DISPLAY = {
    VerificationStatus.DRAFT: "Draft",
    VerificationStatus.SUBMITTED: "Submitted",
    VerificationStatus.VERIFIED: "Verified",
    VerificationStatus.DISPUTED: "Disputed",
    VerificationStatus.RESOLVED: "Resolved",
}


def _empty_metric_fields(
    detection_rule: str = "",
    verification_status: str = "",
) -> dict[str, str]:
    """Return empty metric/algorithm fields for rows without computed metrics."""
    return {
        "Time in Bed (min)": "",
        "Total Sleep Time (min)": "",
        "WASO (min)": "",
        "Sleep Onset Latency (min)": "",
        "Number of Awakenings": "",
        "Avg Awakening Length (min)": "",
        "Sleep Efficiency (%)": "",
        "Movement Index": "",
        "Fragmentation Index": "",
        "Sleep Fragmentation Index": "",
        "Total Activity Counts": "",
        "Non-zero Epochs": "",
        "Algorithm": "",
        "Detection Rule": detection_rule,
        "Verification Status": verification_status,
    }


# =============================================================================
# Column Registry - Single Source of Truth for Export Columns
# =============================================================================


@dataclass(frozen=True)
class ColumnDefinition:
    """Definition of an export column."""

    name: str
    category: str
    description: str
    data_type: str = "string"
    is_default: bool = True


# Define all available export columns
EXPORT_COLUMNS: list[ColumnDefinition] = [
    # File Info
    ColumnDefinition("Filename", "File Info", "Source data filename"),
    ColumnDefinition("File ID", "File Info", "Database file ID", "number"),
    ColumnDefinition("Participant ID", "File Info", "Extracted participant ID"),
    # Period Info
    ColumnDefinition("Study Date", "Period Info", "Study date being scored"),
    ColumnDefinition("Period Index", "Period Info", "Sleep period number (1=first)", "number"),
    ColumnDefinition("Marker Type", "Period Info", "Main Sleep, Nap, or Manual Nonwear"),
    # Time Markers
    ColumnDefinition("Onset Time", "Time Markers", "Sleep onset time (HH:MM)"),
    ColumnDefinition("Offset Time", "Time Markers", "Sleep offset time (HH:MM)"),
    ColumnDefinition("Onset Datetime", "Time Markers", "Full onset datetime", "datetime"),
    ColumnDefinition("Offset Datetime", "Time Markers", "Full offset datetime", "datetime"),
    # Duration Metrics
    ColumnDefinition("Time in Bed (min)", "Duration Metrics", "Total time from onset to offset", "number"),
    ColumnDefinition("Total Sleep Time (min)", "Duration Metrics", "TST - minutes scored as sleep", "number"),
    ColumnDefinition("WASO (min)", "Duration Metrics", "Wake After Sleep Onset minutes", "number"),
    ColumnDefinition("Sleep Onset Latency (min)", "Duration Metrics", "Time to fall asleep", "number"),
    # Awakening Metrics
    ColumnDefinition("Number of Awakenings", "Awakening Metrics", "Count of wake periods", "number"),
    ColumnDefinition("Avg Awakening Length (min)", "Awakening Metrics", "Mean awakening duration", "number"),
    # Quality Indices
    ColumnDefinition("Sleep Efficiency (%)", "Quality Indices", "TST / Time in Bed * 100", "number"),
    ColumnDefinition("Movement Index", "Quality Indices", "Movement indicator", "number"),
    ColumnDefinition("Fragmentation Index", "Quality Indices", "Sleep fragmentation", "number"),
    ColumnDefinition("Sleep Fragmentation Index", "Quality Indices", "Combined fragmentation", "number"),
    # Activity Metrics
    ColumnDefinition("Total Activity Counts", "Activity Metrics", "Sum of activity counts", "number"),
    ColumnDefinition("Non-zero Epochs", "Activity Metrics", "Count of epochs with movement", "number"),
    # Algorithm Info
    ColumnDefinition("Algorithm", "Algorithm Info", "Sleep scoring algorithm used"),
    ColumnDefinition("Detection Rule", "Algorithm Info", "Sleep detection rule active when scored"),
    ColumnDefinition("Verification Status", "Algorithm Info", "Draft, verified, etc."),
    # Annotation Info
    ColumnDefinition("Scored By", "Annotation Info", "Username who created the markers"),
    ColumnDefinition("Is No Sleep", "Annotation Info", "Date marked as no sleep", "boolean"),
    ColumnDefinition("Needs Consensus", "Annotation Info", "Date flagged for consensus review", "boolean"),
    ColumnDefinition("Notes", "Annotation Info", "Free-text annotation notes"),
]

# Group columns by category
COLUMN_CATEGORIES: dict[str, list[str]] = {}
for col in EXPORT_COLUMNS:
    if col.category not in COLUMN_CATEGORIES:
        COLUMN_CATEGORIES[col.category] = []
    COLUMN_CATEGORIES[col.category].append(col.name)

# Default columns (subset for quick export)
DEFAULT_COLUMNS = [col.name for col in EXPORT_COLUMNS if col.is_default]


# =============================================================================
# Export Result
# =============================================================================


@dataclass
class ExportResult:
    """Result of an export operation."""

    success: bool
    csv_content: str = ""
    filename: str = ""
    row_count: int = 0
    file_count: int = 0
    warnings: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)
    # Separate nonwear CSV (populated when nonwear markers exist)
    nonwear_csv_content: str = ""
    nonwear_row_count: int = 0
    nonwear_filename: str = ""


# =============================================================================
# Export Service
# =============================================================================


class ExportService:
    """Service for generating CSV exports from sleep scoring data."""

    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    @staticmethod
    def get_available_columns() -> list[ColumnDefinition]:
        """Get list of all available export columns."""
        return EXPORT_COLUMNS

    @staticmethod
    def get_column_categories() -> dict[str, list[str]]:
        """Get columns grouped by category."""
        return COLUMN_CATEGORIES

    @staticmethod
    def get_default_columns() -> list[str]:
        """Get list of default column names."""
        return DEFAULT_COLUMNS

    async def export_csv(
        self,
        file_ids: list[int],
        date_range: tuple[date, date] | None = None,
        columns: list[str] | None = None,
        include_header: bool = True,
        include_metadata: bool = False,
    ) -> ExportResult:
        """
        Generate CSV export for specified files.

        Produces separate CSVs for sleep and nonwear markers.
        Sleep markers go into csv_content, nonwear into nonwear_csv_content.

        Args:
            file_ids: List of file IDs to export
            date_range: Optional (start_date, end_date) filter
            columns: Column names to include (None = all default columns)
            include_header: Whether to include CSV header row
            include_metadata: Whether to include metadata comments at top

        Returns:
            ExportResult with CSV content and statistics

        """
        result = ExportResult(success=False)

        if not file_ids:
            result.errors.append("No files specified for export")
            return result

        # Determine columns to export
        export_columns = columns or DEFAULT_COLUMNS

        # Validate columns
        valid_column_names = {col.name for col in EXPORT_COLUMNS}
        invalid_columns = [c for c in export_columns if c not in valid_column_names]
        if invalid_columns:
            result.warnings.append(f"Skipping invalid columns: {', '.join(invalid_columns)}")
            export_columns = [c for c in export_columns if c in valid_column_names]

        if not export_columns:
            result.errors.append("No valid columns selected for export")
            return result

        try:
            sleep_rows, nonwear_rows = await self._fetch_export_data(file_ids, date_range)

            if not sleep_rows and not nonwear_rows:
                result.warnings.append("No data found for selected files and date range")
                result.success = True
                result.csv_content = ""
                return result

            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")

            # Generate sleep CSV
            if sleep_rows:
                result.csv_content = self._generate_csv(sleep_rows, export_columns, include_header, include_metadata)
                result.row_count = len(sleep_rows)
                result.file_count = len({row.get("File ID") for row in sleep_rows})
                result.filename = f"sleep_export_{timestamp}.csv"

            # Generate nonwear CSV (separate file)
            if nonwear_rows:
                result.nonwear_csv_content = self._generate_csv(nonwear_rows, export_columns, include_header, include_metadata)
                result.nonwear_row_count = len(nonwear_rows)
                result.nonwear_filename = f"nonwear_export_{timestamp}.csv"
                if not result.file_count:
                    result.file_count = len({row.get("File ID") for row in nonwear_rows})

            result.success = True

            logger.info(
                "Export completed: %d sleep rows, %d nonwear rows from %d files",
                result.row_count,
                result.nonwear_row_count,
                result.file_count,
            )
            return result

        except Exception as e:
            logger.exception("Export failed: %s", e)
            result.errors.append(f"Export failed: {e!s}")
            return result

    async def _fetch_export_data(
        self,
        file_ids: list[int],
        date_range: tuple[date, date] | None = None,
    ) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
        """Fetch and join data from markers, metrics, and annotations tables."""
        sleep_rows: list[dict[str, Any]] = []
        nonwear_rows: list[dict[str, Any]] = []

        # Unpack date range once for use in both annotation and marker queries
        start_date, end_date = date_range or (None, None)

        # Get files info
        files_result = await self.db.execute(select(File).where(File.id.in_(file_ids)))
        files = {f.id: f for f in files_result.scalars().all()}

        # Get annotation flags (is_no_sleep, needs_consensus) per file/date
        ann_query = select(UserAnnotation).where(
            and_(
                UserAnnotation.file_id.in_(file_ids),
                UserAnnotation.status == VerificationStatus.SUBMITTED,
            )
        )
        if start_date and end_date:
            ann_query = ann_query.where(
                and_(
                    UserAnnotation.analysis_date >= start_date,
                    UserAnnotation.analysis_date <= end_date,
                )
            )
        ann_result = await self.db.execute(ann_query)
        annotations = ann_result.scalars().all()
        # Build lookup: (file_id, analysis_date) -> annotation
        ann_lookup: dict[tuple[int, Any], UserAnnotation] = {}
        for ann in annotations:
            key = (ann.file_id, ann.analysis_date)
            # Keep the most recent annotation per file/date
            if key not in ann_lookup or (ann.updated_at and ann_lookup[key].updated_at and ann.updated_at > ann_lookup[key].updated_at):
                ann_lookup[key] = ann

        # Build sleep marker query
        marker_query = select(Marker).where(
            and_(
                Marker.file_id.in_(file_ids),
                Marker.marker_category == MarkerCategory.SLEEP,
                Marker.end_timestamp.isnot(None),  # Only complete markers
            )
        )

        if start_date and end_date:
            marker_query = marker_query.where(
                and_(
                    Marker.analysis_date >= start_date,
                    Marker.analysis_date <= end_date,
                )
            )

        marker_query = marker_query.order_by(Marker.file_id, Marker.analysis_date, Marker.period_index)

        markers_result = await self.db.execute(marker_query)
        markers = markers_result.scalars().all()

        # Batch-fetch all metrics for these file_ids (and date range) in one query
        metrics_query = select(SleepMetric).where(SleepMetric.file_id.in_(file_ids))
        if start_date and end_date:
            metrics_query = metrics_query.where(
                and_(
                    SleepMetric.analysis_date >= start_date,
                    SleepMetric.analysis_date <= end_date,
                )
            )
        metrics_result = await self.db.execute(metrics_query)
        all_metrics = metrics_result.scalars().all()
        # Build lookup: (file_id, analysis_date, period_index) -> SleepMetric
        metrics_lookup: dict[tuple[int, Any, int | None], SleepMetric] = {}
        for m in all_metrics:
            metrics_lookup[(m.file_id, m.analysis_date, m.period_index)] = m

        # Track which file/date pairs have marker rows (to find no-sleep dates)
        dates_with_markers: set[tuple[int, Any]] = set()

        for marker in markers:
            file = files.get(marker.file_id)
            if not file:
                continue

            dates_with_markers.add((marker.file_id, marker.analysis_date))

            # Get annotation flags for this file/date
            ann = ann_lookup.get((marker.file_id, marker.analysis_date))

            # Get metrics from pre-fetched lookup
            metrics = metrics_lookup.get((marker.file_id, marker.analysis_date, marker.period_index))

            # Convert timestamps to datetime
            onset_dt = datetime.fromtimestamp(marker.start_timestamp, tz=UTC) if marker.start_timestamp else None
            offset_dt = datetime.fromtimestamp(marker.end_timestamp, tz=UTC) if marker.end_timestamp else None

            row = {
                # File Info
                "Filename": file.filename,
                "File ID": file.id,
                "Participant ID": file.participant_id or "",
                # Period Info
                "Study Date": str(marker.analysis_date) if marker.analysis_date else "",
                "Period Index": marker.period_index,
                "Marker Type": _MARKER_TYPE_DISPLAY.get(marker.marker_type, marker.marker_type or ""),
                # Time Markers
                "Onset Time": onset_dt.strftime("%H:%M") if onset_dt else "",
                "Offset Time": offset_dt.strftime("%H:%M") if offset_dt else "",
                "Onset Datetime": onset_dt.strftime("%Y-%m-%d %H:%M:%S") if onset_dt else "",
                "Offset Datetime": offset_dt.strftime("%Y-%m-%d %H:%M:%S") if offset_dt else "",
                # Annotation Info
                "Scored By": marker.created_by or "",
                "Is No Sleep": "True" if (ann and ann.is_no_sleep) else "False",
                "Needs Consensus": "True" if (ann and ann.needs_consensus) else "False",
                "Notes": (ann.notes or "") if ann else "",
            }

            # Add metrics if available
            if metrics:
                algo_raw = metrics.algorithm_type or ""
                rule_raw = metrics.detection_rule or (ann.detection_rule if ann else None) or ""
                row.update(
                    {
                        "Time in Bed (min)": self._format_number(metrics.time_in_bed_minutes),
                        "Total Sleep Time (min)": self._format_number(metrics.total_sleep_time_minutes),
                        "WASO (min)": self._format_number(metrics.waso_minutes),
                        "Sleep Onset Latency (min)": self._format_number(metrics.sleep_onset_latency_minutes),
                        "Number of Awakenings": metrics.number_of_awakenings,
                        "Avg Awakening Length (min)": self._format_number(metrics.average_awakening_length_minutes),
                        "Sleep Efficiency (%)": self._format_number(metrics.sleep_efficiency),
                        "Movement Index": self._format_number(metrics.movement_index),
                        "Fragmentation Index": self._format_number(metrics.fragmentation_index),
                        "Sleep Fragmentation Index": self._format_number(metrics.sleep_fragmentation_index),
                        "Total Activity Counts": metrics.total_activity,
                        "Non-zero Epochs": metrics.nonzero_epochs,
                        "Algorithm": _ALGORITHM_DISPLAY.get(algo_raw, algo_raw),
                        "Detection Rule": _DETECTION_RULE_DISPLAY.get(rule_raw, rule_raw),
                        "Verification Status": _VERIFICATION_DISPLAY.get(
                            metrics.verification_status or VerificationStatus.DRAFT,
                            metrics.verification_status or "Draft",
                        ),
                    }
                )
            else:
                rule_raw = (ann.detection_rule if ann else None) or ""
                row.update(_empty_metric_fields(
                    detection_rule=_DETECTION_RULE_DISPLAY.get(rule_raw, rule_raw),
                    verification_status="Draft",
                ))

            sleep_rows.append(row)

        # Query nonwear markers (manual only, exclude sensor/read-only)
        nonwear_query = select(Marker).where(and_(
            Marker.file_id.in_(file_ids),
            Marker.marker_category == MarkerCategory.NONWEAR,
            Marker.exclude_sensor_nonwear_filter(),
            Marker.end_timestamp.isnot(None),
        ))
        if start_date and end_date:
            nonwear_query = nonwear_query.where(and_(
                Marker.analysis_date >= start_date,
                Marker.analysis_date <= end_date,
            ))
        nonwear_query = nonwear_query.order_by(Marker.file_id, Marker.analysis_date, Marker.period_index)
        nonwear_result = await self.db.execute(nonwear_query)
        nonwear_markers = nonwear_result.scalars().all()

        for nw in nonwear_markers:
            file = files.get(nw.file_id)
            if not file:
                continue

            # NOTE: Do NOT add nonwear dates to dates_with_markers here.
            # dates_with_markers gates no-sleep row suppression (line ~482),
            # and a date can have nonwear markers AND be marked as no-sleep.

            ann = ann_lookup.get((nw.file_id, nw.analysis_date))

            onset_dt = datetime.fromtimestamp(nw.start_timestamp, tz=UTC) if nw.start_timestamp else None
            offset_dt = datetime.fromtimestamp(nw.end_timestamp, tz=UTC) if nw.end_timestamp else None

            nonwear_rows.append({
                "Filename": file.filename,
                "File ID": file.id,
                "Participant ID": file.participant_id or "",
                "Study Date": str(nw.analysis_date) if nw.analysis_date else "",
                "Period Index": nw.period_index if nw.period_index is not None else "",
                "Marker Type": _MARKER_TYPE_DISPLAY.get(nw.marker_type, nw.marker_type or "Manual Nonwear"),
                "Onset Time": onset_dt.strftime("%H:%M") if onset_dt else "",
                "Offset Time": offset_dt.strftime("%H:%M") if offset_dt else "",
                "Onset Datetime": onset_dt.strftime("%Y-%m-%d %H:%M:%S") if onset_dt else "",
                "Offset Datetime": offset_dt.strftime("%Y-%m-%d %H:%M:%S") if offset_dt else "",
                "Scored By": nw.created_by or "",
                "Is No Sleep": "True" if (ann and ann.is_no_sleep) else "False",
                "Needs Consensus": "True" if (ann and ann.needs_consensus) else "False",
                "Notes": (ann.notes or "") if ann else "",
                **_empty_metric_fields(),
            })

        # Add rows for no-sleep dates (have annotation but no marker rows)
        for key, ann in ann_lookup.items():
            if key in dates_with_markers:
                continue
            if not ann.is_no_sleep:
                continue
            file = files.get(ann.file_id)
            if not file:
                continue
            rule_raw = ann.detection_rule or ""
            sleep_rows.append({
                "Filename": file.filename,
                "File ID": file.id,
                "Participant ID": file.participant_id or "",
                "Study Date": str(ann.analysis_date),
                "Period Index": "",
                "Marker Type": "",
                "Onset Time": "",
                "Offset Time": "",
                "Onset Datetime": "",
                "Offset Datetime": "",
                "Scored By": ann.username or "",
                "Is No Sleep": "True",
                "Needs Consensus": "True" if ann.needs_consensus else "False",
                "Notes": ann.notes or "",
                **_empty_metric_fields(
                    detection_rule=_DETECTION_RULE_DISPLAY.get(rule_raw, rule_raw),
                ),
            })

        def _sort_key(r: dict[str, Any]) -> tuple:
            return (
                r.get("Filename", ""),
                r.get("Study Date", ""),
                r.get("Period Index") if isinstance(r.get("Period Index"), int) else -1,
            )

        sleep_rows.sort(key=_sort_key)
        nonwear_rows.sort(key=_sort_key)

        return sleep_rows, nonwear_rows

    @staticmethod
    def _format_number(value: float | None, precision: int = 2) -> str:
        """Format number for CSV output."""
        if value is None:
            return ""
        if isinstance(value, int):
            return str(value)
        return f"{value:.{precision}f}"

    def _generate_csv(
        self,
        rows: list[dict[str, Any]],
        columns: list[str],
        include_header: bool = True,
        include_metadata: bool = False,
    ) -> str:
        """Generate CSV string from rows."""
        output = io.StringIO()

        # Add metadata comments if requested
        if include_metadata:
            output.write("#\n")
            output.write("# Sleep Scoring Export\n")
            output.write(f"# Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
            output.write(f"# Total Rows: {len(rows)}\n")
            output.write(f"# Files: {len({r.get('File ID') for r in rows})}\n")
            output.write("#\n")

        writer = csv.DictWriter(
            output,
            fieldnames=columns,
            extrasaction="ignore",
        )

        if include_header:
            writer.writeheader()

        for row in rows:
            # Sanitize values to prevent CSV injection
            sanitized_row = {k: self._sanitize_csv_value(v) for k, v in row.items()}
            writer.writerow(sanitized_row)

        return output.getvalue()

    @staticmethod
    def _sanitize_csv_value(value: Any) -> Any:
        """Sanitize value to prevent CSV formula injection."""
        if not isinstance(value, str):
            return value
        if value and value[0] in ("=", "+", "-", "@", "\t", "\r"):
            return "'" + value
        return value
