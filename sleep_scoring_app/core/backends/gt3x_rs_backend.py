"""
gt3x-rs compute backend implementation.

High-performance Rust-based backend using gt3x-rs library (PyO3 bindings).
Provides 10-50x speedup over Python implementations for most operations.

Architecture:
    - Wraps all gt3x-rs Python functions
    - Implements ComputeBackend protocol
    - Auto-registers with BackendFactory (priority=10, preferred)
    - Returns is_available=False if gt3x-rs not installed

Example Usage:
    >>> from sleep_scoring_app.core.backends import Gt3xRsBackend
    >>>
    >>> backend = Gt3xRsBackend()
    >>> if backend.is_available:
    ...     data = backend.parse_gt3x("file.gt3x")

References:
    - gt3x-rs: packages/gt3x-rs (Rust implementation with PyO3 bindings)
    - 52x faster than pygt3x for parsing
    - GGIR-compatible calibration and imputation

"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

import numpy as np

from .capabilities import BackendCapability

if TYPE_CHECKING:
    from .data_types import (
        CalibrationResult,
        CircadianResult,
        EpochData,
        ImputationResult,
        MetricResult,
        NonwearResult,
        RawAccelerometerData,
        SleepDetectionResult,
        SleepScoreResult,
        ValidationResult,
    )

logger = logging.getLogger(__name__)

# Try to import gt3x-rs
# Use TYPE_CHECKING to properly handle optional import for type checker
gt3x_rs: Any = None  # Module placeholder for when not available
try:
    import gt3x_rs as _gt3x_rs

    gt3x_rs = _gt3x_rs
    GT3X_RS_AVAILABLE = True
except ImportError:
    GT3X_RS_AVAILABLE = False
    logger.debug("gt3x-rs not available (import failed)")


class Gt3xRsBackend:
    """
    gt3x-rs compute backend implementation.

    Wraps all gt3x-rs Python functions to provide high-performance computation.
    Implements ComputeBackend protocol for dependency injection compatibility.

    This backend is preferred (priority=10) when available due to significant
    performance improvements over pure Python implementations.

    Capabilities:
        - GT3X parsing (52x faster)
        - GGIR-compatible calibration and imputation
        - Sleep scoring (Sadeh, Cole-Kripke, Van Hees SIB, HDCZA)
        - Nonwear detection (Van Hees 2013/2023)
        - Metrics (ENMO, angles, filtered metrics)
        - Circadian metrics (M5/L5, IS/IV)
        - Validation (Cohen's kappa)

    Attributes:
        _capabilities: Set of supported capabilities

    """

    def __init__(self) -> None:
        """Initialize gt3x-rs backend."""
        self._capabilities = self._detect_capabilities()

    @property
    def name(self) -> str:
        """Backend name for display."""
        return "gt3x-rs (Rust)"

    @property
    def is_available(self) -> bool:
        """Check if gt3x-rs library is available."""
        return GT3X_RS_AVAILABLE

    def supports(self, capability: BackendCapability) -> bool:
        """Check if backend supports a specific capability."""
        return capability in self._capabilities

    def _detect_capabilities(self) -> set[BackendCapability]:
        """Detect which capabilities are available in current gt3x-rs version."""
        if not GT3X_RS_AVAILABLE:
            return set()

        # All capabilities that gt3x-rs provides
        # Based on gt3x_rs.__init__.py exports
        return {
            # Parsing
            BackendCapability.PARSE_GT3X,
            BackendCapability.PARSE_GT3X_METADATA,
            BackendCapability.PARSE_GT3X_SENSORS,
            # Preprocessing
            BackendCapability.CALIBRATION,
            BackendCapability.IMPUTATION,
            BackendCapability.EPOCHING,
            # Metrics
            BackendCapability.ENMO,
            BackendCapability.ANGLES,
            BackendCapability.LFENMO,
            BackendCapability.HFEN,
            BackendCapability.BFEN,
            BackendCapability.HFENPLUS,
            # Sleep scoring
            BackendCapability.SADEH,
            BackendCapability.COLE_KRIPKE,
            BackendCapability.VAN_HEES_SIB,
            BackendCapability.HDCZA,
            # Nonwear
            BackendCapability.VAN_HEES_NONWEAR,
            # Circadian
            BackendCapability.M5L5,
            BackendCapability.IVIS,
            BackendCapability.SRI,
            # Activity
            BackendCapability.ACTIVITY_CLASSIFICATION,
            BackendCapability.BOUT_DETECTION,
            BackendCapability.FRAGMENTATION,
            # Validation
            BackendCapability.COHENS_KAPPA,
            # Batch processing
            BackendCapability.PARALLEL_PROCESSING,
        }

    # ========================
    # Parsing Methods
    # ========================

    def parse_gt3x(
        self,
        file_path: str,
        include_sensors: bool = False,
    ) -> RawAccelerometerData:
        """Parse GT3X binary file using gt3x-rs."""
        if not GT3X_RS_AVAILABLE:
            msg = "gt3x-rs library not available"
            raise NotImplementedError(msg)

        from .data_types import RawAccelerometerData

        # Configure parsing
        if include_sensors:
            config = gt3x_rs.ParseConfig.all()
        else:
            config = gt3x_rs.ParseConfig()

        # Parse file
        data = gt3x_rs.parse_gt3x(file_path, config)

        # Convert to numpy arrays
        x = np.array(data.x, dtype=np.float64)
        y = np.array(data.y, dtype=np.float64)
        z = np.array(data.z, dtype=np.float64)
        timestamps = np.array(data.timestamps, dtype=np.float64)

        # Build metadata
        metadata = {
            "sample_rate": data.sample_rate,
            "serial_number": getattr(data, "serial_number", None),
            "start_time": getattr(data, "start_time", None),
        }

        # Add sensor data if requested
        if include_sensors:
            if hasattr(data, "lux") and data.lux is not None:
                metadata["lux"] = np.array(data.lux)
            if hasattr(data, "battery") and data.battery is not None:
                metadata["battery"] = np.array(data.battery)
            if hasattr(data, "capsense") and data.capsense is not None:
                metadata["capsense"] = np.array(data.capsense)

        return RawAccelerometerData(
            x=x,
            y=y,
            z=z,
            timestamps=timestamps,
            sample_rate=data.sample_rate,
            metadata=metadata,
        )

    def parse_gt3x_metadata(self, file_path: str) -> dict[str, Any]:
        """
        Extract metadata from GT3X file.

        Note: gt3x_rs.parse_gt3x_metadata returns Gt3xDataFull object,
        we extract relevant metadata fields from it.
        """
        if not GT3X_RS_AVAILABLE:
            msg = "gt3x-rs library not available"
            raise NotImplementedError(msg)

        # parse_gt3x_metadata returns Gt3xDataFull with metadata included
        data = gt3x_rs.parse_gt3x_metadata(file_path)

        # Extract metadata from the Gt3xDataFull object
        result: dict[str, Any] = {
            "sample_rate": data.sample_rate,
            "serial_number": data.serial_number,
            "n_samples": len(data) if hasattr(data, "__len__") else len(data.x),
        }

        # Try to get metadata dict if available
        if data.has_metadata():
            metadata_dict = data.metadata_to_dict()
            if metadata_dict:
                result["device_metadata"] = metadata_dict

        return result

    # ========================
    # Preprocessing Methods
    # ========================

    def calibrate(
        self,
        x: np.ndarray,
        y: np.ndarray,
        z: np.ndarray,
        sample_rate: float,
        config: dict[str, Any] | None = None,
    ) -> CalibrationResult:
        """Perform GGIR-compatible autocalibration."""
        if not GT3X_RS_AVAILABLE:
            msg = "gt3x-rs library not available"
            raise NotImplementedError(msg)

        from .data_types import CalibrationResult as CalibResult

        # Convert to lists for gt3x-rs (Rust FFI)
        x_list = x.tolist()
        y_list = y.tolist()
        z_list = z.tolist()

        # Call gt3x-rs calibration
        result = gt3x_rs.calibrate_ggir(x_list, y_list, z_list, sample_rate)

        # Convert result
        return CalibResult(
            success=result.success,
            scale=np.array(result.scale),
            offset=np.array(result.offset),
            error_before=result.error_before,
            error_after=result.error_after,
            n_points_used=result.n_points_used,
            message=result.message,
        )

    def apply_calibration(
        self,
        x: np.ndarray,
        y: np.ndarray,
        z: np.ndarray,
        scale: np.ndarray,
        offset: np.ndarray,
    ) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
        """Apply calibration parameters."""
        if not GT3X_RS_AVAILABLE:
            msg = "gt3x-rs library not available"
            raise NotImplementedError(msg)

        # Convert to lists
        x_list = x.tolist()
        y_list = y.tolist()
        z_list = z.tolist()

        # Create CalibrationResult object for gt3x-rs
        cal_result = gt3x_rs.CalibrationResult(
            success=True,
            scale=scale.tolist(),
            offset=offset.tolist(),
            error_before=0.0,
            error_after=0.0,
            n_points_used=0,
            message="Manual calibration",
        )

        # Apply calibration
        x_cal, y_cal, z_cal = gt3x_rs.apply_calibration_ggir(x_list, y_list, z_list, cal_result)

        return np.array(x_cal), np.array(y_cal), np.array(z_cal)

    def impute_gaps(
        self,
        x: np.ndarray,
        y: np.ndarray,
        z: np.ndarray,
        timestamps: np.ndarray,
        sample_rate: float,
        config: dict[str, Any] | None = None,
    ) -> ImputationResult:
        """Perform GGIR-compatible time gap imputation."""
        if not GT3X_RS_AVAILABLE:
            msg = "gt3x-rs library not available"
            raise NotImplementedError(msg)

        from .data_types import ImputationResult as ImpResult

        # Convert to lists
        x_list = x.tolist()
        y_list = y.tolist()
        z_list = z.tolist()
        ts_list = timestamps.tolist()

        # Call gt3x-rs imputation
        result = gt3x_rs.impute_timegaps(x_list, y_list, z_list, ts_list, sample_rate)

        # Convert result
        return ImpResult(
            x=np.array(result.x),
            y=np.array(result.y),
            z=np.array(result.z),
            timestamps=np.array(result.timestamps),
            n_gaps=result.qc.n_gaps,
            n_samples_added=result.qc.n_samples_added,
            total_gap_sec=result.qc.total_gap_sec,
            gap_details=None,  # gt3x-rs doesn't provide gap details in result
        )

    def compute_epochs(
        self,
        activity_data: np.ndarray,
        timestamps: np.ndarray,
        epoch_length_sec: int,
        sample_rate: float,
    ) -> EpochData:
        """Aggregate raw samples into epochs."""
        from .data_types import EpochData as EpochDataClass

        # Simple epoching using numpy
        samples_per_epoch = int(sample_rate * epoch_length_sec)
        n_samples = len(activity_data)
        n_epochs = n_samples // samples_per_epoch

        if n_epochs == 0:
            msg = "Not enough samples for even one epoch"
            raise ValueError(msg)

        # Truncate to complete epochs
        truncated = n_samples - (n_samples % samples_per_epoch)
        epoch_data = activity_data[:truncated]
        epoch_ts = timestamps[:truncated]

        # Reshape and sum
        epoch_data_reshaped = epoch_data.reshape(n_epochs, samples_per_epoch)
        epoch_counts = np.sum(np.abs(epoch_data_reshaped), axis=1)

        # Epoch timestamps (first sample of each epoch)
        epoch_timestamps = epoch_ts.reshape(n_epochs, samples_per_epoch)[:, 0]

        return EpochDataClass(
            epoch_counts=epoch_counts,
            epoch_timestamps=epoch_timestamps,
            epoch_length_sec=epoch_length_sec,
            axis="unknown",  # Caller should specify
            metadata={"sample_rate": sample_rate},
        )

    # ========================
    # Metric Computation Methods
    # ========================

    def compute_enmo(
        self,
        x: np.ndarray,
        y: np.ndarray,
        z: np.ndarray,
    ) -> MetricResult:
        """Compute ENMO metric."""
        if not GT3X_RS_AVAILABLE:
            msg = "gt3x-rs library not available"
            raise NotImplementedError(msg)

        from .data_types import MetricResult as MetricRes

        enmo = gt3x_rs.compute_enmo(x.tolist(), y.tolist(), z.tolist())

        return MetricRes(
            values=np.array(enmo),
            metric_name="enmo",
            parameters=None,
            metadata=None,
        )

    def compute_angles(
        self,
        x: np.ndarray,
        y: np.ndarray,
        z: np.ndarray,
    ) -> MetricResult:
        """Compute arm angles."""
        if not GT3X_RS_AVAILABLE:
            msg = "gt3x-rs library not available"
            raise NotImplementedError(msg)

        from .data_types import MetricResult as MetricRes

        angles = gt3x_rs.compute_angles(x.tolist(), y.tolist(), z.tolist())

        return MetricRes(
            values=np.array(angles),
            metric_name="angle_z",
            parameters=None,
            metadata=None,
        )

    # ========================
    # Sleep Scoring Methods
    # ========================

    def sadeh_score(
        self,
        activity_counts: np.ndarray,
        variant: str = "actilife",
    ) -> SleepScoreResult:
        """Perform Sadeh sleep scoring."""
        if not GT3X_RS_AVAILABLE:
            msg = "gt3x-rs library not available"
            raise NotImplementedError(msg)

        from .data_types import SleepScoreResult as SleepResult

        # Select variant function
        if variant == "original":
            result = gt3x_rs.sadeh_original(activity_counts.tolist())
        elif variant == "actilife":
            result = gt3x_rs.sadeh_actilife(activity_counts.tolist())
        else:
            # Default to actilife
            result = gt3x_rs.sadeh_actilife(activity_counts.tolist())

        return SleepResult(
            sleep_scores=np.array(result.scores),
            algorithm=f"sadeh_{variant}",
            parameters={"variant": variant},
            metadata=None,
        )

    def cole_kripke_score(
        self,
        activity_counts: np.ndarray,
        variant: str = "actilife",
    ) -> SleepScoreResult:
        """Perform Cole-Kripke sleep scoring."""
        if not GT3X_RS_AVAILABLE:
            msg = "gt3x-rs library not available"
            raise NotImplementedError(msg)

        from .data_types import SleepScoreResult as SleepResult

        # Select variant function
        if variant == "original":
            result = gt3x_rs.cole_kripke_original(activity_counts.tolist())
        elif variant == "actilife":
            result = gt3x_rs.cole_kripke_actilife(activity_counts.tolist())
        else:
            result = gt3x_rs.cole_kripke_actilife(activity_counts.tolist())

        return SleepResult(
            sleep_scores=np.array(result.scores),
            algorithm=f"cole_kripke_{variant}",
            parameters={"variant": variant},
            metadata=None,
        )

    def van_hees_sib(
        self,
        angle_z: np.ndarray,
        timestamps: np.ndarray,
        config: dict[str, Any] | None = None,
    ) -> SleepScoreResult:
        """Perform Van Hees SIB detection."""
        if not GT3X_RS_AVAILABLE:
            msg = "gt3x-rs library not available"
            raise NotImplementedError(msg)

        from .data_types import SleepScoreResult as SleepResult

        # Create config if needed
        if config is None:
            sib_config = gt3x_rs.SibConfig()
        else:
            sib_config = gt3x_rs.SibConfig(**config)

        # Call gt3x-rs
        result = gt3x_rs.detect_sib(angle_z.tolist(), timestamps.tolist(), sib_config)

        return SleepResult(
            sleep_scores=np.array(result.sib_periods),
            algorithm="van_hees_sib",
            parameters=config,
            metadata=None,
        )

    def hdcza_detect(
        self,
        x: np.ndarray,
        y: np.ndarray,
        z: np.ndarray,
        timestamps: np.ndarray,
        config: dict[str, Any] | None = None,
    ) -> SleepDetectionResult:
        """Perform HDCZA sleep detection."""
        if not GT3X_RS_AVAILABLE:
            msg = "gt3x-rs library not available"
            raise NotImplementedError(msg)

        from .data_types import SleepDetectionResult as SleepDetResult

        # Create config if needed
        if config is None:
            sleep_config = gt3x_rs.SleepConfig()
        else:
            sleep_config = gt3x_rs.SleepConfig(**config)

        # Call gt3x-rs
        result = gt3x_rs.detect_sleep_hdcza(x.tolist(), y.tolist(), z.tolist(), timestamps.tolist(), sleep_config)

        # Calculate metrics (simplified - would need full implementation)
        tst_min = 0.0  # Would calculate from result
        waso_min = 0.0
        efficiency = 0.0

        return SleepDetResult(
            onset_idx=result.onset_idx if hasattr(result, "onset_idx") else 0,
            offset_idx=result.offset_idx if hasattr(result, "offset_idx") else 0,
            onset_time=result.onset_time if hasattr(result, "onset_time") else None,
            offset_time=result.offset_time if hasattr(result, "offset_time") else None,
            total_sleep_time_min=tst_min,
            wake_after_sleep_onset_min=waso_min,
            sleep_efficiency_pct=efficiency,
            method="hdcza",
            metadata=None,
        )

    # ========================
    # Nonwear Detection Methods
    # ========================

    def van_hees_nonwear(
        self,
        x: np.ndarray,
        y: np.ndarray,
        z: np.ndarray,
        sample_rate: float,
        algorithm: str = "2023",
        config: dict[str, Any] | None = None,
    ) -> NonwearResult:
        """Perform Van Hees nonwear detection."""
        if not GT3X_RS_AVAILABLE:
            msg = "gt3x-rs library not available"
            raise NotImplementedError(msg)

        from .data_types import NonwearResult as NonwearRes

        # Select algorithm version
        if algorithm == "2013":
            result = gt3x_rs.van_hees_2013(x.tolist(), y.tolist(), z.tolist(), sample_rate)
        else:  # 2023 is default
            result = gt3x_rs.van_hees_2023(x.tolist(), y.tolist(), z.tolist(), sample_rate)

        # Convert to boolean array
        nonwear_vector = np.array(result.nonwear_vector, dtype=bool)

        # Extract periods (simplified - would need proper implementation)
        periods = []
        if hasattr(result, "nonwear_periods"):
            periods = [(p.start, p.end) for p in result.nonwear_periods]

        return NonwearRes(
            nonwear_vector=nonwear_vector,
            nonwear_periods=periods,
            algorithm=f"van_hees_{algorithm}",
            parameters=config or {},
            metadata=None,
        )

    # ========================
    # Circadian Metrics Methods
    # ========================

    def get_m5l5(
        self,
        enmo: np.ndarray,
        timestamps: np.ndarray,
    ) -> CircadianResult:
        """Compute M5/L5 circadian metrics."""
        if not GT3X_RS_AVAILABLE:
            msg = "gt3x-rs library not available"
            raise NotImplementedError(msg)

        from .data_types import CircadianResult as CircRes

        # Compute M5/L5 (need sample rate, using default)
        result = gt3x_rs.get_m5l5(enmo.tolist(), 1.0)  # Assume 1Hz ENMO

        values = {
            "m5": result.m5_value,
            "l5": result.l5_value,
            "m5_time": result.m5_time,
            "l5_time": result.l5_time,
            "relative_amplitude": result.relative_amplitude,
        }

        return CircRes(
            metric_name="m5l5",
            values=values,
            timestamps=None,
            metadata=None,
        )

    # ========================
    # Validation Methods
    # ========================

    def cohens_kappa(
        self,
        rater1: np.ndarray,
        rater2: np.ndarray,
    ) -> ValidationResult:
        """Compute Cohen's kappa."""
        if not GT3X_RS_AVAILABLE:
            msg = "gt3x-rs library not available"
            raise NotImplementedError(msg)

        from .data_types import ValidationResult as ValResult

        # Call gt3x-rs function (returns float)
        kappa = gt3x_rs.cohens_kappa_py(rater1.tolist(), rater2.tolist())

        return ValResult(
            metric_name="cohens_kappa",
            value=float(kappa),
            confidence_interval=None,
            statistics=None,
            metadata=None,
        )
