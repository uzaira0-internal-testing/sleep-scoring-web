#!/usr/bin/env python3
"""
Validation framework for seamless activity data switching.
Provides comprehensive before/after state comparison and validation utilities.
"""

from __future__ import annotations

import hashlib
import time
from collections import namedtuple
from dataclasses import asdict, dataclass
from typing import TYPE_CHECKING, Any, Protocol
from unittest.mock import Mock

from sleep_scoring_app.core.constants import ViewMode

# ParticipantKey was removed from dataclasses - use simple namedtuple for tests
ParticipantKey = namedtuple("ParticipantKey", ["participant_id", "study_code", "group"])

if TYPE_CHECKING:
    import numpy as np


class StateValidator(Protocol):
    """Protocol for state validation functions."""

    def validate(self, before_state: dict[str, Any], after_state: dict[str, Any]) -> ValidationResult:
        """Validate state transition."""
        ...


@dataclass
class ValidationResult:
    """Result of state validation."""

    is_valid: bool
    errors: list[str]
    warnings: list[str]
    metrics: dict[str, Any]
    validation_time_ms: float


@dataclass
class SwitchingContext:
    """Context information for switching operation."""

    operation_type: str  # "mode_change", "data_source_change", "participant_change"
    source_mode: ViewMode
    target_mode: ViewMode
    source_data_type: str  # "database", "csv"
    target_data_type: str
    participant_key: ParticipantKey | None
    timestamp: float
    additional_info: dict[str, Any]


@dataclass
class PlotState:
    """Complete plot widget state for validation."""

    view_range_x: tuple[float, float]
    view_range_y: tuple[float, float]
    zoom_level: float
    pan_position: tuple[float, float]
    data_points: int
    data_hash: str
    markers: list[dict[str, Any]]
    algorithm_overlays: list[str]
    view_mode: ViewMode
    filename: str | None
    plot_items_count: int
    axis_ranges: dict[str, tuple[float, float]]


@dataclass
class MemoryState:
    """Memory state for validation."""

    rss_mb: float
    vms_mb: float
    cached_data_count: int
    cache_memory_mb: float
    gc_stats: dict[str, int]


@dataclass
class PerformanceMetrics:
    """Performance metrics for switching operations."""

    total_time_ms: float
    data_load_time_ms: float
    ui_update_time_ms: float
    state_preservation_time_ms: float
    memory_cleanup_time_ms: float
    throughput_records_per_sec: float


class StateComparisonFramework:
    """Framework for comparing before/after states during switching."""

    def __init__(self) -> None:
        self.validators: dict[str, StateValidator] = {}
        self.tolerance_settings = self._get_default_tolerances()
        self.validation_history: list[dict[str, Any]] = []

    def register_validator(self, name: str, validator: StateValidator):
        """Register a state validator."""
        self.validators[name] = validator

    def capture_plot_state(self, plot_widget: Any) -> PlotState:
        """Capture complete plot widget state."""
        try:
            view_range = plot_widget.vb.viewRange() if hasattr(plot_widget, "vb") else [[0, 1], [0, 1]]

            return PlotState(
                view_range_x=tuple(view_range[0]),
                view_range_y=tuple(view_range[1]),
                zoom_level=self._calculate_zoom_level(view_range),
                pan_position=(view_range[0][0], view_range[1][0]),
                data_points=len(getattr(plot_widget, "activity_data", [])),
                data_hash=self._calculate_data_hash(getattr(plot_widget, "activity_data", [])),
                markers=getattr(plot_widget, "sleep_markers", []).copy(),
                algorithm_overlays=self._get_algorithm_overlays(plot_widget),
                view_mode=getattr(plot_widget, "current_view_hours", ViewMode.HOURS_24),
                filename=getattr(plot_widget, "current_filename", None),
                plot_items_count=len(plot_widget.listDataItems()) if hasattr(plot_widget, "listDataItems") else 0,
                axis_ranges=self._get_axis_ranges(plot_widget),
            )
        except Exception:
            return PlotState(
                view_range_x=(0, 1),
                view_range_y=(0, 1),
                zoom_level=1.0,
                pan_position=(0, 0),
                data_points=0,
                data_hash="error",
                markers=[],
                algorithm_overlays=[],
                view_mode=ViewMode.HOURS_24,
                filename=None,
                plot_items_count=0,
                axis_ranges={},
            )

    def capture_memory_state(self) -> MemoryState:
        """Capture memory state."""
        try:
            import gc
            import os

            import psutil

            process = psutil.Process(os.getpid())
            memory_info = process.memory_info()

            return MemoryState(
                rss_mb=memory_info.rss / 1024 / 1024,
                vms_mb=memory_info.vms / 1024 / 1024,
                cached_data_count=0,  # Would need actual cache implementation
                cache_memory_mb=0.0,
                gc_stats={
                    "generation_0": gc.get_count()[0],
                    "generation_1": gc.get_count()[1],
                    "generation_2": gc.get_count()[2],
                    "collections": len(gc.get_stats()) if hasattr(gc, "get_stats") else 0,
                },
            )
        except Exception:
            return MemoryState(rss_mb=0.0, vms_mb=0.0, cached_data_count=0, cache_memory_mb=0.0, gc_stats={})

    def validate_switching_operation(
        self,
        before_plot: PlotState,
        after_plot: PlotState,
        before_memory: MemoryState,
        after_memory: MemoryState,
        context: SwitchingContext,
        performance: PerformanceMetrics,
    ) -> ValidationResult:
        """Validate complete switching operation."""
        start_time = time.perf_counter()

        errors = []
        warnings = []
        metrics = {}

        # Run all registered validators
        for validator_name, validator in self.validators.items():
            try:
                state_dict_before = {
                    "plot": asdict(before_plot),
                    "memory": asdict(before_memory),
                    "context": asdict(context),
                    "performance": asdict(performance),
                }

                state_dict_after = {
                    "plot": asdict(after_plot),
                    "memory": asdict(after_memory),
                    "context": asdict(context),
                    "performance": asdict(performance),
                }

                result = validator.validate(state_dict_before, state_dict_after)

                if not result.is_valid:
                    errors.extend([f"{validator_name}: {error}" for error in result.errors])

                warnings.extend([f"{validator_name}: {warning}" for warning in result.warnings])
                metrics[validator_name] = result.metrics

            except Exception as e:
                errors.append(f"{validator_name}: Validation failed with exception: {e!s}")

        # Overall validation metrics
        validation_time = (time.perf_counter() - start_time) * 1000

        # Record validation history
        validation_record = {
            "timestamp": context.timestamp,
            "operation_type": context.operation_type,
            "is_valid": len(errors) == 0,
            "error_count": len(errors),
            "warning_count": len(warnings),
            "validation_time_ms": validation_time,
            "performance_metrics": asdict(performance),
        }
        self.validation_history.append(validation_record)

        return ValidationResult(is_valid=len(errors) == 0, errors=errors, warnings=warnings, metrics=metrics, validation_time_ms=validation_time)

    def _get_default_tolerances(self) -> dict[str, Any]:
        """Get default tolerance settings for validation."""
        return {
            "zoom_tolerance": 0.1,  # 10% tolerance for zoom preservation
            "pan_tolerance": 0.05,  # 5% tolerance for pan preservation
            "memory_growth_mb": 100,  # Max 100MB memory growth per operation
            "performance_threshold_ms": 500,  # Max 500ms for switching operation
            "marker_position_tolerance": 1000,  # 1000ms tolerance for marker positions
            "data_integrity_sample_size": 1000,  # Sample size for data integrity checks
        }

    def _calculate_zoom_level(self, view_range: list[list[float]]) -> float:
        """Calculate zoom level from view range."""
        try:
            x_span = view_range[0][1] - view_range[0][0]
            y_span = view_range[1][1] - view_range[1][0]
            return x_span / y_span if y_span != 0 else 1.0
        except (IndexError, ZeroDivisionError):
            return 1.0

    def _calculate_data_hash(self, data: list | np.ndarray) -> str:
        """Calculate hash of data for integrity checking."""
        if not data:
            return "empty"

        try:
            # Sample data for performance
            sample_size = min(1000, len(data))
            sample = data[:sample_size]

            # Convert to string and hash
            data_str = str(list(sample))
            return hashlib.md5(data_str.encode()).hexdigest()[:16]
        except Exception:
            return "error"

    def _get_algorithm_overlays(self, plot_widget: Any) -> list[str]:
        """Get list of algorithm overlays in plot."""
        try:
            if hasattr(plot_widget, "listDataItems"):
                items = plot_widget.listDataItems()
                overlays = []

                for item in items:
                    if hasattr(item, "name") and item.name:
                        if "sadeh" in item.name.lower() or "choi" in item.name.lower():
                            overlays.append(item.name)

                return overlays

            return []
        except Exception:
            return []

    def _get_axis_ranges(self, plot_widget: Any) -> dict[str, tuple[float, float]]:
        """Get axis ranges from plot widget."""
        try:
            ranges = {}

            if hasattr(plot_widget, "getAxis"):
                x_axis = plot_widget.getAxis("bottom")
                y_axis = plot_widget.getAxis("left")

                if hasattr(x_axis, "range"):
                    ranges["x"] = tuple(x_axis.range)

                if hasattr(y_axis, "range"):
                    ranges["y"] = tuple(y_axis.range)

            return ranges
        except Exception:
            return {}


class ZoomPreservationValidator:
    """Validator for zoom level preservation."""

    def __init__(self, tolerance: float = 0.1) -> None:
        self.tolerance = tolerance

    def validate(self, before_state: dict[str, Any], after_state: dict[str, Any]) -> ValidationResult:
        """Validate zoom preservation."""
        errors = []
        warnings = []
        metrics = {}

        before_zoom = before_state["plot"]["zoom_level"]
        after_zoom = after_state["plot"]["zoom_level"]

        zoom_change = abs(after_zoom - before_zoom) / max(before_zoom, 0.001)
        metrics["zoom_change_ratio"] = zoom_change
        metrics["before_zoom"] = before_zoom
        metrics["after_zoom"] = after_zoom

        # Check if zoom change is within tolerance
        if zoom_change > self.tolerance:
            operation_type = after_state["context"]["operation_type"]

            if operation_type == "mode_change":
                # For view mode changes, some zoom adjustment is expected
                if zoom_change > 0.5:  # 50% tolerance for mode changes
                    warnings.append(f"Large zoom change during mode change: {zoom_change:.3f}")
            else:
                # For same-mode operations, zoom should be preserved more strictly
                errors.append(f"Zoom level changed unexpectedly: {zoom_change:.3f} > {self.tolerance}")

        return ValidationResult(is_valid=len(errors) == 0, errors=errors, warnings=warnings, metrics=metrics, validation_time_ms=0.0)


class MarkerPreservationValidator:
    """Validator for marker preservation."""

    def __init__(self, position_tolerance: float = 1000) -> None:
        self.position_tolerance = position_tolerance

    def validate(self, before_state: dict[str, Any], after_state: dict[str, Any]) -> ValidationResult:
        """Validate marker preservation."""
        errors = []
        warnings = []
        metrics = {}

        before_markers = before_state["plot"]["markers"]
        after_markers = after_state["plot"]["markers"]

        metrics["before_marker_count"] = len(before_markers)
        metrics["after_marker_count"] = len(after_markers)

        # Check marker count preservation
        if len(after_markers) != len(before_markers):
            errors.append(f"Marker count changed: {len(before_markers)} -> {len(after_markers)}")
            return ValidationResult(True, errors, warnings, metrics, 0.0)

        # Check individual marker preservation
        markers_preserved = 0
        position_shifts = []

        for i, (before_marker, after_marker) in enumerate(zip(before_markers, after_markers, strict=False)):
            # Check type preservation
            if before_marker.get("type") != after_marker.get("type"):
                errors.append(f"Marker {i} type changed: {before_marker.get('type')} -> {after_marker.get('type')}")
                continue

            # Check label preservation
            if before_marker.get("label") != after_marker.get("label"):
                errors.append(f"Marker {i} label changed: {before_marker.get('label')} -> {after_marker.get('label')}")
                continue

            # Check position preservation
            before_time = before_marker.get("time", 0)
            after_time = after_marker.get("time", 0)
            position_shift = abs(after_time - before_time)
            position_shifts.append(position_shift)

            if position_shift > self.position_tolerance:
                warnings.append(f"Marker {i} position shifted by {position_shift:.0f}ms")
            else:
                markers_preserved += 1

        metrics["markers_preserved"] = markers_preserved
        metrics["avg_position_shift"] = sum(position_shifts) / len(position_shifts) if position_shifts else 0
        metrics["max_position_shift"] = max(position_shifts) if position_shifts else 0

        return ValidationResult(is_valid=len(errors) == 0, errors=errors, warnings=warnings, metrics=metrics, validation_time_ms=0.0)


class DataIntegrityValidator:
    """Validator for data integrity."""

    def __init__(self, sample_size: int = 1000) -> None:
        self.sample_size = sample_size

    def validate(self, before_state: dict[str, Any], after_state: dict[str, Any]) -> ValidationResult:
        """Validate data integrity."""
        errors = []
        warnings = []
        metrics = {}

        before_hash = before_state["plot"]["data_hash"]
        after_hash = after_state["plot"]["data_hash"]
        before_points = before_state["plot"]["data_points"]
        after_points = after_state["plot"]["data_points"]

        metrics["before_data_points"] = before_points
        metrics["after_data_points"] = after_points
        metrics["before_hash"] = before_hash
        metrics["after_hash"] = after_hash

        operation_type = after_state["context"]["operation_type"]

        if operation_type == "participant_change":
            # Different participant should have different data
            if before_hash == after_hash and before_points == after_points:
                warnings.append("Data appears unchanged after participant switch")
        elif operation_type == "mode_change":
            # Mode change might have different data sizes
            source_mode = after_state["context"]["source_mode"]
            target_mode = after_state["context"]["target_mode"]

            if source_mode != target_mode:
                # Different view modes might have different data sizes
                expected_ratio = 2.0 if target_mode == "HOURS_48" and source_mode == "HOURS_24" else 0.5
                actual_ratio = after_points / max(before_points, 1)

                if abs(actual_ratio - expected_ratio) > 0.2:  # 20% tolerance
                    warnings.append(f"Unexpected data size change: ratio {actual_ratio:.2f}, expected ~{expected_ratio:.2f}")

        # Check for corrupted data indicators
        if after_hash == "error":
            errors.append("Data corruption detected after switching")

        if after_points == 0 and before_points > 0:
            errors.append("Data lost during switching")

        return ValidationResult(is_valid=len(errors) == 0, errors=errors, warnings=warnings, metrics=metrics, validation_time_ms=0.0)


class MemoryUsageValidator:
    """Validator for memory usage during switching."""

    def __init__(self, max_growth_mb: float = 100) -> None:
        self.max_growth_mb = max_growth_mb

    def validate(self, before_state: dict[str, Any], after_state: dict[str, Any]) -> ValidationResult:
        """Validate memory usage."""
        errors = []
        warnings = []
        metrics = {}

        before_memory = before_state["memory"]["rss_mb"]
        after_memory = after_state["memory"]["rss_mb"]
        memory_growth = after_memory - before_memory

        metrics["before_memory_mb"] = before_memory
        metrics["after_memory_mb"] = after_memory
        metrics["memory_growth_mb"] = memory_growth

        # Check memory growth
        if memory_growth > self.max_growth_mb:
            errors.append(f"Excessive memory growth: {memory_growth:.2f} MB > {self.max_growth_mb} MB")
        elif memory_growth > self.max_growth_mb * 0.7:
            warnings.append(f"High memory growth: {memory_growth:.2f} MB")

        # Check for memory leaks (continuous growth)
        if memory_growth > 50 and memory_growth / before_memory > 0.2:  # 20% growth
            warnings.append(f"Potential memory leak: {memory_growth:.2f} MB ({memory_growth / before_memory * 100:.1f}% growth)")

        return ValidationResult(is_valid=len(errors) == 0, errors=errors, warnings=warnings, metrics=metrics, validation_time_ms=0.0)


class PerformanceValidator:
    """Validator for switching performance."""

    def __init__(self, max_time_ms: float = 500) -> None:
        self.max_time_ms = max_time_ms

    def validate(self, before_state: dict[str, Any], after_state: dict[str, Any]) -> ValidationResult:
        """Validate switching performance."""
        errors = []
        warnings = []
        metrics = {}

        performance = after_state["performance"]
        total_time = performance["total_time_ms"]

        metrics.update(performance)

        # Check total time
        if total_time > self.max_time_ms:
            errors.append(f"Switching too slow: {total_time:.1f} ms > {self.max_time_ms} ms")
        elif total_time > self.max_time_ms * 0.7:
            warnings.append(f"Switching approaching threshold: {total_time:.1f} ms")

        # Check component performance
        data_load_time = performance.get("data_load_time_ms", 0)
        ui_update_time = performance.get("ui_update_time_ms", 0)

        if data_load_time > total_time * 0.8:
            warnings.append(f"Data loading dominates switching time: {data_load_time:.1f} ms / {total_time:.1f} ms")

        if ui_update_time > total_time * 0.3:
            warnings.append(f"UI updates are slow: {ui_update_time:.1f} ms / {total_time:.1f} ms")

        return ValidationResult(is_valid=len(errors) == 0, errors=errors, warnings=warnings, metrics=metrics, validation_time_ms=0.0)


class TestStateValidationFramework:
    """Test the state validation framework."""

    def test_framework_initialization(self):
        """Test framework initialization."""
        framework = StateComparisonFramework()

        assert len(framework.validators) == 0
        assert "zoom_tolerance" in framework.tolerance_settings
        assert len(framework.validation_history) == 0

    def test_validator_registration(self):
        """Test validator registration."""
        framework = StateComparisonFramework()

        # Register validators
        framework.register_validator("zoom", ZoomPreservationValidator())
        framework.register_validator("markers", MarkerPreservationValidator())
        framework.register_validator("data", DataIntegrityValidator())
        framework.register_validator("memory", MemoryUsageValidator())
        framework.register_validator("performance", PerformanceValidator())

        assert len(framework.validators) == 5
        assert "zoom" in framework.validators
        assert "markers" in framework.validators
        assert "data" in framework.validators
        assert "memory" in framework.validators
        assert "performance" in framework.validators

    def test_plot_state_capture(self):
        """Test plot state capture."""
        framework = StateComparisonFramework()

        # Mock plot widget
        mock_plot = Mock()
        mock_plot.vb.viewRange.return_value = [[0, 86400], [0, 300]]
        mock_plot.activity_data = [1, 2, 3, 4, 5]
        mock_plot.sleep_markers = [{"type": "onset", "time": 1000}]
        mock_plot.current_view_hours = ViewMode.HOURS_24
        mock_plot.current_filename = "test.csv"
        mock_plot.listDataItems.return_value = [Mock(), Mock()]
        mock_plot.getAxis.return_value.range = [0, 86400]

        state = framework.capture_plot_state(mock_plot)

        assert isinstance(state, PlotState)
        assert state.view_range_x == (0, 86400)
        assert state.view_range_y == (0, 300)
        assert state.data_points == 5
        assert len(state.markers) == 1
        assert state.view_mode == ViewMode.HOURS_24
        assert state.filename == "test.csv"
        assert state.plot_items_count == 2

    def test_memory_state_capture(self):
        """Test memory state capture."""
        framework = StateComparisonFramework()

        state = framework.capture_memory_state()

        assert isinstance(state, MemoryState)
        assert state.rss_mb >= 0
        assert state.vms_mb >= 0
        assert isinstance(state.gc_stats, dict)

    def test_zoom_preservation_validation(self):
        """Test zoom preservation validation."""
        validator = ZoomPreservationValidator(tolerance=0.1)

        # Test preserved zoom
        before_state = {"plot": {"zoom_level": 1.5}, "memory": {}, "context": {"operation_type": "participant_change"}, "performance": {}}

        after_state = {
            "plot": {"zoom_level": 1.52},  # Small change within tolerance
            "memory": {},
            "context": {"operation_type": "participant_change"},
            "performance": {},
        }

        result = validator.validate(before_state, after_state)

        assert result.is_valid
        assert len(result.errors) == 0
        assert "zoom_change_ratio" in result.metrics

    def test_marker_preservation_validation(self):
        """Test marker preservation validation."""
        validator = MarkerPreservationValidator(position_tolerance=1000)

        # Test preserved markers
        markers = [{"type": "onset", "time": 75600, "label": "Sleep Onset"}, {"type": "offset", "time": 104400, "label": "Sleep Offset"}]

        before_state = {"plot": {"markers": markers}, "memory": {}, "context": {}, "performance": {}}

        after_state = {
            "plot": {"markers": markers.copy()},  # Same markers
            "memory": {},
            "context": {},
            "performance": {},
        }

        result = validator.validate(before_state, after_state)

        assert result.is_valid
        assert len(result.errors) == 0
        assert result.metrics["markers_preserved"] == 2

    def test_data_integrity_validation(self):
        """Test data integrity validation."""
        validator = DataIntegrityValidator()

        # Test data preservation for same operation
        before_state = {
            "plot": {"data_hash": "abc123", "data_points": 2880},
            "memory": {},
            "context": {"operation_type": "mode_change", "source_mode": "HOURS_24", "target_mode": "HOURS_24"},
            "performance": {},
        }

        after_state = {
            "plot": {
                "data_hash": "abc123",  # Same hash
                "data_points": 2880,  # Same points
            },
            "memory": {},
            "context": {"operation_type": "mode_change", "source_mode": "HOURS_24", "target_mode": "HOURS_24"},
            "performance": {},
        }

        result = validator.validate(before_state, after_state)

        assert result.is_valid
        assert len(result.errors) == 0

    def test_memory_usage_validation(self):
        """Test memory usage validation."""
        validator = MemoryUsageValidator(max_growth_mb=100)

        # Test acceptable memory usage
        before_state = {"plot": {}, "memory": {"rss_mb": 150.0}, "context": {}, "performance": {}}

        after_state = {
            "plot": {},
            "memory": {"rss_mb": 180.0},  # 30MB growth - acceptable
            "context": {},
            "performance": {},
        }

        result = validator.validate(before_state, after_state)

        assert result.is_valid
        assert len(result.errors) == 0
        assert result.metrics["memory_growth_mb"] == 30.0

    def test_performance_validation(self):
        """Test performance validation."""
        validator = PerformanceValidator(max_time_ms=500)

        # Test acceptable performance
        performance_metrics = {
            "total_time_ms": 250.0,
            "data_load_time_ms": 100.0,
            "ui_update_time_ms": 50.0,
            "state_preservation_time_ms": 20.0,
            "memory_cleanup_time_ms": 10.0,
            "throughput_records_per_sec": 10000.0,
        }

        before_state = {"plot": {}, "memory": {}, "context": {}, "performance": performance_metrics}

        after_state = {"plot": {}, "memory": {}, "context": {}, "performance": performance_metrics}

        result = validator.validate(before_state, after_state)

        assert result.is_valid
        assert len(result.errors) == 0
        assert result.metrics["total_time_ms"] == 250.0

    def test_complete_validation_workflow(self):
        """Test complete validation workflow."""
        framework = StateComparisonFramework()

        # Register all validators
        framework.register_validator("zoom", ZoomPreservationValidator())
        framework.register_validator("markers", MarkerPreservationValidator())
        framework.register_validator("data", DataIntegrityValidator())
        framework.register_validator("memory", MemoryUsageValidator())
        framework.register_validator("performance", PerformanceValidator())

        # Create test states
        before_plot = PlotState(
            view_range_x=(0, 86400),
            view_range_y=(0, 300),
            zoom_level=1.5,
            pan_position=(0, 0),
            data_points=2880,
            data_hash="abc123",
            markers=[{"type": "onset", "time": 1000}],
            algorithm_overlays=["sadeh"],
            view_mode=ViewMode.HOURS_24,
            filename="test.csv",
            plot_items_count=2,
            axis_ranges={"x": (0, 86400), "y": (0, 300)},
        )

        after_plot = PlotState(
            view_range_x=(0, 86400),
            view_range_y=(0, 300),
            zoom_level=1.52,  # Slight change
            pan_position=(0, 0),
            data_points=2880,
            data_hash="abc123",
            markers=[{"type": "onset", "time": 1000}],
            algorithm_overlays=["sadeh"],
            view_mode=ViewMode.HOURS_24,
            filename="test.csv",
            plot_items_count=2,
            axis_ranges={"x": (0, 86400), "y": (0, 300)},
        )

        before_memory = MemoryState(rss_mb=150.0, vms_mb=200.0, cached_data_count=5, cache_memory_mb=10.0, gc_stats={"generation_0": 100})

        after_memory = MemoryState(
            rss_mb=160.0,  # Small growth
            vms_mb=210.0,
            cached_data_count=5,
            cache_memory_mb=10.0,
            gc_stats={"generation_0": 105},
        )

        context = SwitchingContext(
            operation_type="participant_change",
            source_mode=ViewMode.HOURS_24,
            target_mode=ViewMode.HOURS_24,
            source_data_type="database",
            target_data_type="database",
            participant_key=ParticipantKey("4000", "BO", "G1"),
            timestamp=time.time(),
            additional_info={},
        )

        performance = PerformanceMetrics(
            total_time_ms=250.0,
            data_load_time_ms=100.0,
            ui_update_time_ms=50.0,
            state_preservation_time_ms=20.0,
            memory_cleanup_time_ms=10.0,
            throughput_records_per_sec=10000.0,
        )

        # Run validation
        result = framework.validate_switching_operation(before_plot, after_plot, before_memory, after_memory, context, performance)

        assert result.is_valid
        assert len(result.errors) == 0
        assert len(result.metrics) == 5  # All validators
        assert len(framework.validation_history) == 1
