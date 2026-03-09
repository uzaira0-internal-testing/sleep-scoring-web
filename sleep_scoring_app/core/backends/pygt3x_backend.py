"""
PyGt3x compute backend implementation.

Python fallback backend using pygt3x and existing Python algorithm implementations.
Used when gt3x-rs is not available or explicitly requested.

Architecture:
    - Uses pygt3x for GT3X parsing
    - Uses existing Python implementations for algorithms
    - Implements ComputeBackend protocol
    - Auto-registers with BackendFactory (priority=50, fallback)
    - Returns is_available=False if pygt3x not installed

Example Usage:
    >>> from sleep_scoring_app.core.backends import PyGt3xBackend
    >>>
    >>> backend = PyGt3xBackend()
    >>> if backend.is_available:
    ...     data = backend.parse_gt3x("file.gt3x")

References:
    - pygt3x: Python library for GT3X parsing
    - sleep_scoring_app.preprocessing: Calibration and imputation modules
    - sleep_scoring_app.core.algorithms: Algorithm implementations

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

# Try to import pygt3x
# Use a placeholder type to avoid type checker issues with optional import
FileReader: Any = None
try:
    from pygt3x.reader import FileReader as _FileReader

    FileReader = _FileReader
    PYGT3X_AVAILABLE = True
except ImportError:
    PYGT3X_AVAILABLE = False
    logger.debug("pygt3x not available (import failed)")


class PyGt3xBackend:
    """
    PyGt3x compute backend implementation.

    Python fallback backend that uses pygt3x for parsing and existing Python
    implementations for preprocessing and algorithms.

    This backend is slower than gt3x-rs but provides complete fallback
    functionality when Rust library is not available.

    Capabilities:
        - GT3X parsing (via pygt3x)
        - GGIR-compatible calibration (Python implementation)
        - GGIR-compatible imputation (Python implementation)
        - Partial algorithm support (Sadeh, Cole-Kripke via existing code)
        - Basic metrics (ENMO, angles via numpy)

    Note:
        Some advanced features (HDCZA, Van Hees nonwear, circadian metrics)
        are not implemented in Python and will raise NotImplementedError.

    Attributes:
        _capabilities: Set of supported capabilities

    """

    def __init__(self) -> None:
        """Initialize PyGt3x backend."""
        self._capabilities = self._detect_capabilities()

    @property
    def name(self) -> str:
        """Backend name for display."""
        return "PyGt3x (Python)"

    @property
    def is_available(self) -> bool:
        """Check if pygt3x library is available."""
        return PYGT3X_AVAILABLE

    def supports(self, capability: BackendCapability) -> bool:
        """Check if backend supports a specific capability."""
        return capability in self._capabilities

    def _detect_capabilities(self) -> set[BackendCapability]:
        """Detect which capabilities are available."""
        if not PYGT3X_AVAILABLE:
            return set()

        # Capabilities provided by Python implementations
        return {
            # Parsing (via pygt3x)
            BackendCapability.PARSE_GT3X,
            BackendCapability.PARSE_GT3X_METADATA,
            # Preprocessing (via sleep_scoring_app.preprocessing)
            BackendCapability.CALIBRATION,
            BackendCapability.IMPUTATION,
            BackendCapability.EPOCHING,
            # Basic metrics (via numpy)
            BackendCapability.ENMO,
            BackendCapability.ANGLES,
            # Sleep scoring (via existing implementations)
            # Note: Would need to check if algorithms are available
            # BackendCapability.SADEH,  # Available via SadehAlgorithm
            # BackendCapability.COLE_KRIPKE,  # Available via ColeKripkeAlgorithm
        }

    # ========================
    # Parsing Methods
    # ========================

    def parse_gt3x(
        self,
        file_path: str,
        include_sensors: bool = False,
    ) -> RawAccelerometerData:
        """Parse GT3X binary file using pygt3x."""
        if not PYGT3X_AVAILABLE:
            msg = "pygt3x library not available"
            raise NotImplementedError(msg)

        from .data_types import RawAccelerometerData

        # Parse using pygt3x
        with FileReader(str(file_path)) as reader:
            # Load data with calibration to get g-units
            df = reader.to_pandas(calibrate=True)

            # Extract metadata
            sample_rate = reader.info.sample_rate
            serial_number = getattr(reader.info, "serial_number", "UNKNOWN")
            start_time = reader.info.start_date
            timezone_offset = getattr(reader.info, "timezone", None)

            # Extract accelerometer data
            x = df["X"].to_numpy()
            y = df["Y"].to_numpy()
            z = df["Z"].to_numpy()

            # Timestamps from index
            timestamps = df.index.to_numpy()

        # Build metadata
        metadata = {
            "sample_rate": sample_rate,
            "serial_number": serial_number,
            "start_time": start_time,
            "timezone_offset": timezone_offset,
        }

        # Convert timestamps to float seconds if needed
        if np.issubdtype(timestamps.dtype, np.datetime64):
            ts_seconds = timestamps.astype("datetime64[ns]").astype(np.float64) / 1e9
        else:
            ts_seconds = timestamps.astype(np.float64)

        return RawAccelerometerData(
            x=x,
            y=y,
            z=z,
            timestamps=ts_seconds,
            sample_rate=sample_rate,
            metadata=metadata,
        )

    def parse_gt3x_metadata(self, file_path: str) -> dict[str, Any]:
        """Extract metadata from GT3X file."""
        if not PYGT3X_AVAILABLE:
            msg = "pygt3x library not available"
            raise NotImplementedError(msg)

        with FileReader(str(file_path)) as reader:
            return {
                "serial_number": getattr(reader.info, "serial_number", "UNKNOWN"),
                "sample_rate": reader.info.sample_rate,
                "start_time": reader.info.start_date,
                "timezone_offset": getattr(reader.info, "timezone", None),
                "device_type": getattr(reader.info, "device_type", None),
                "firmware": getattr(reader.info, "firmware_version", None),
            }

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
        from .data_types import CalibrationResult as CalibResult

        try:
            from sleep_scoring_app.preprocessing.calibration import (
                CalibrationConfig,
                calibrate,
            )

            # Stack into (N, 3) array
            acc_data = np.column_stack([x, y, z])

            # Create config
            if config is None:
                cal_config = CalibrationConfig()
            else:
                cal_config = CalibrationConfig(**config)

            # Call calibration
            result = calibrate(acc_data, sample_rate, cal_config)

            return CalibResult(
                success=result.success,
                scale=result.scale,
                offset=result.offset,
                error_before=result.error_before,
                error_after=result.error_after,
                n_points_used=result.n_points_used,
                message=result.message,
            )

        except ImportError as e:
            msg = f"Calibration module not available: {e}"
            raise NotImplementedError(msg) from e

    def apply_calibration(
        self,
        x: np.ndarray,
        y: np.ndarray,
        z: np.ndarray,
        scale: np.ndarray,
        offset: np.ndarray,
    ) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
        """Apply calibration parameters."""
        try:
            from sleep_scoring_app.preprocessing.calibration import apply_calibration

            # Stack into (N, 3) array
            acc_data = np.column_stack([x, y, z])

            # Apply calibration
            calibrated = apply_calibration(acc_data, scale, offset)

            # Ensure we return numpy arrays (not Series/DataFrame slices)
            return (
                np.asarray(calibrated[:, 0]),
                np.asarray(calibrated[:, 1]),
                np.asarray(calibrated[:, 2]),
            )

        except ImportError as e:
            msg = f"Calibration module not available: {e}"
            raise NotImplementedError(msg) from e

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
        from .data_types import ImputationResult as ImpResult

        try:
            from sleep_scoring_app.preprocessing.imputation import (
                ImputationConfig,
                impute_timegaps,
            )

            # Stack into (N, 3) array
            acc_data = np.column_stack([x, y, z])

            # Create config
            if config is None:
                imp_config = ImputationConfig()
            else:
                imp_config = ImputationConfig(**config)

            # Call imputation
            result = impute_timegaps(acc_data, timestamps, sample_rate, imp_config)

            return ImpResult(
                x=result.data[:, 0],
                y=result.data[:, 1],
                z=result.data[:, 2],
                timestamps=result.timestamps,
                n_gaps=result.n_gaps,
                n_samples_added=result.n_samples_added,
                total_gap_sec=result.total_gap_sec,
                gap_details=None,
            )

        except ImportError as e:
            msg = f"Imputation module not available: {e}"
            raise NotImplementedError(msg) from e

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
            axis="unknown",
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
        from .data_types import MetricResult as MetricRes

        # ENMO = max(0, sqrt(x^2 + y^2 + z^2) - 1)
        magnitude = np.sqrt(x**2 + y**2 + z**2)
        enmo = np.maximum(0.0, magnitude - 1.0)

        return MetricRes(
            values=enmo,
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
        from .data_types import MetricResult as MetricRes

        # Angle-z = atan2(z, sqrt(x^2 + y^2)) * 180/pi
        xy_magnitude = np.sqrt(x**2 + y**2)
        angle_z = np.arctan2(z, xy_magnitude) * 180.0 / np.pi

        return MetricRes(
            values=angle_z,
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
        # Not implemented - would need to import and use SadehAlgorithm
        msg = "Sadeh scoring not directly implemented in PyGt3xBackend. Use SadehAlgorithm from sleep_scoring_app.core.algorithms instead."
        raise NotImplementedError(msg)

    def cole_kripke_score(
        self,
        activity_counts: np.ndarray,
        variant: str = "actilife",
    ) -> SleepScoreResult:
        """Perform Cole-Kripke sleep scoring."""
        # Not implemented - would need to import and use ColeKripkeAlgorithm
        msg = "Cole-Kripke scoring not directly implemented in PyGt3xBackend. Use ColeKripkeAlgorithm from sleep_scoring_app.core.algorithms instead."
        raise NotImplementedError(msg)

    def van_hees_sib(
        self,
        angle_z: np.ndarray,
        timestamps: np.ndarray,
        config: dict[str, Any] | None = None,
    ) -> SleepScoreResult:
        """Perform Van Hees SIB detection."""
        # Not implemented - would need Python implementation
        msg = "Van Hees SIB not implemented in Python backend. Use VanHees2015SIB from sleep_scoring_app.core.algorithms or gt3x-rs backend."
        raise NotImplementedError(msg)

    def hdcza_detect(
        self,
        x: np.ndarray,
        y: np.ndarray,
        z: np.ndarray,
        timestamps: np.ndarray,
        config: dict[str, Any] | None = None,
    ) -> SleepDetectionResult:
        """Perform HDCZA sleep detection."""
        # Not implemented in Python
        msg = "HDCZA not implemented in Python backend. Use gt3x-rs backend."
        raise NotImplementedError(msg)

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
        # Not implemented in Python
        msg = "Van Hees nonwear not implemented in Python backend. Use gt3x-rs backend."
        raise NotImplementedError(msg)

    # ========================
    # Circadian Metrics Methods
    # ========================

    def get_m5l5(
        self,
        enmo: np.ndarray,
        timestamps: np.ndarray,
    ) -> CircadianResult:
        """Compute M5/L5 circadian metrics."""
        # Not implemented in Python
        msg = "M5/L5 metrics not implemented in Python backend. Use gt3x-rs backend."
        raise NotImplementedError(msg)

    # ========================
    # Validation Methods
    # ========================

    def cohens_kappa(
        self,
        rater1: np.ndarray,
        rater2: np.ndarray,
    ) -> ValidationResult:
        """Compute Cohen's kappa."""
        from .data_types import ValidationResult as ValResult

        # Simple Cohen's kappa implementation
        # Agreement
        n = len(rater1)
        observed_agreement = np.sum(rater1 == rater2) / n

        # Expected agreement
        p1_yes = np.sum(rater1 == 1) / n
        p1_no = 1 - p1_yes
        p2_yes = np.sum(rater2 == 1) / n
        p2_no = 1 - p2_yes

        expected_agreement = (p1_yes * p2_yes) + (p1_no * p2_no)

        # Kappa
        if expected_agreement == 1.0:
            kappa = 1.0
        else:
            kappa = (observed_agreement - expected_agreement) / (1.0 - expected_agreement)

        return ValResult(
            metric_name="cohens_kappa",
            value=float(kappa),
            confidence_interval=None,
            statistics={
                "observed_agreement": observed_agreement,
                "expected_agreement": expected_agreement,
            },
            metadata=None,
        )
