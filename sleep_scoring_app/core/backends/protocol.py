"""
Compute backend protocol for dependency injection.

This protocol defines the interface that all compute backends must implement.
Enables swapping between gt3x-rs (Rust) and Python implementations without
changing application logic.

Architecture:
    - Protocol defines the contract for compute backends
    - Implementations: Gt3xRsBackend (preferred), PyGt3xBackend (fallback)
    - Factory creates instances with automatic backend selection
    - Services accept protocol type, not concrete implementations

Example Usage:
    >>> from sleep_scoring_app.core.backends import BackendFactory, BackendCapability
    >>>
    >>> # Create backend (auto-selects best available)
    >>> backend = BackendFactory.create()
    >>>
    >>> # Check capabilities
    >>> if backend.supports(BackendCapability.PARSE_GT3X):
    ...     data = backend.parse_gt3x("file.gt3x")
    >>>
    >>> # Use in dependency injection
    >>> def process_file(backend: ComputeBackend, file_path: str):
    ...     raw_data = backend.parse_gt3x(file_path)
    ...     calibrated = backend.calibrate(raw_data)
    ...     return calibrated

References:
    - gt3x-rs: packages/gt3x-rs (Rust implementation)
    - pygt3x: Python fallback for parsing
    - GGIR: R package for validation

"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, Protocol, runtime_checkable

if TYPE_CHECKING:
    import numpy as np

    from .capabilities import BackendCapability
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


@runtime_checkable
class ComputeBackend(Protocol):
    """
    Protocol for compute backends.

    All compute backends (gt3x-rs, pygt3x, etc.) must implement this interface.
    The protocol is runtime_checkable to allow isinstance() checks for validation.

    Not all backends need to implement all methods. Backends should return
    NotImplementedError for unsupported operations, and declare support via
    the supports() method.

    Properties:
        name: Human-readable backend name for display
        is_available: Whether backend is available (libraries installed)

    Methods:
        supports: Check if backend supports a specific capability
        parse_gt3x: Parse GT3X binary file
        calibrate: GGIR-compatible sphere calibration
        apply_calibration: Apply calibration parameters
        impute_gaps: GGIR-compatible time gap imputation
        compute_epochs: Aggregate raw samples to epochs
        compute_enmo: Compute ENMO metric
        compute_angles: Compute arm angles
        sadeh_score: Sadeh sleep scoring
        cole_kripke_score: Cole-Kripke sleep scoring
        van_hees_sib: Van Hees sustained inactivity bouts
        hdcza_detect: HDCZA sleep detection
        van_hees_nonwear: Van Hees nonwear detection
        get_m5l5: M5/L5 circadian metrics
        cohens_kappa: Cohen's kappa agreement

    """

    @property
    def name(self) -> str:
        """
        Backend name for display and identification.

        Returns:
            Human-readable backend name (e.g., "gt3x-rs (Rust)", "PyGt3x (Python)")

        """
        ...

    @property
    def is_available(self) -> bool:
        """
        Check if backend is available for use.

        Returns:
            True if backend libraries are installed and functional

        """
        ...

    def supports(self, capability: BackendCapability) -> bool:
        """
        Check if backend supports a specific capability.

        Args:
            capability: Capability to check

        Returns:
            True if capability is supported, False otherwise

        Example:
            >>> if backend.supports(BackendCapability.PARSE_GT3X):
            ...     data = backend.parse_gt3x("file.gt3x")

        """
        ...

    # ========================
    # Parsing Methods
    # ========================

    def parse_gt3x(
        self,
        file_path: str,
        include_sensors: bool = False,
    ) -> RawAccelerometerData:
        """
        Parse GT3X binary file to extract accelerometer data.

        Args:
            file_path: Path to GT3X file
            include_sensors: If True, include lux/battery/capsense in metadata

        Returns:
            RawAccelerometerData with X, Y, Z, timestamps, and metadata

        Raises:
            NotImplementedError: If backend doesn't support GT3X parsing
            FileNotFoundError: If file doesn't exist
            ValueError: If file is corrupted or invalid

        """
        ...

    def parse_gt3x_metadata(self, file_path: str) -> dict[str, Any]:
        """
        Extract metadata from GT3X file without loading full data.

        Args:
            file_path: Path to GT3X file

        Returns:
            Dictionary with device info, sample rate, start time, etc.

        Raises:
            NotImplementedError: If backend doesn't support metadata extraction

        """
        ...

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
        """
        Perform GGIR-compatible sphere-fitting autocalibration.

        Finds stationary periods and optimizes scale/offset to ensure
        vector magnitude equals 1g at rest.

        Args:
            x: X-axis acceleration in g
            y: Y-axis acceleration in g
            z: Z-axis acceleration in g
            sample_rate: Sampling frequency in Hz
            config: Optional calibration configuration

        Returns:
            CalibrationResult with scale, offset, and quality metrics

        Raises:
            NotImplementedError: If backend doesn't support calibration

        """
        ...

    def apply_calibration(
        self,
        x: np.ndarray,
        y: np.ndarray,
        z: np.ndarray,
        scale: np.ndarray,
        offset: np.ndarray,
    ) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
        """
        Apply calibration parameters to raw data.

        Args:
            x: X-axis raw data
            y: Y-axis raw data
            z: Z-axis raw data
            scale: Scale factors [x_scale, y_scale, z_scale]
            offset: Offset values [x_offset, y_offset, z_offset]

        Returns:
            Tuple of (calibrated_x, calibrated_y, calibrated_z)

        Raises:
            NotImplementedError: If backend doesn't support calibration

        """
        ...

    def impute_gaps(
        self,
        x: np.ndarray,
        y: np.ndarray,
        z: np.ndarray,
        timestamps: np.ndarray,
        sample_rate: float,
        config: dict[str, Any] | None = None,
    ) -> ImputationResult:
        """
        Perform GGIR-compatible time gap imputation.

        Uses row replication method (np.repeat equivalent) to fill gaps.
        Critical for matching GGIR nonwear detection output.

        Args:
            x: X-axis acceleration
            y: Y-axis acceleration
            z: Z-axis acceleration
            timestamps: Timestamp array (Unix seconds or datetime64)
            sample_rate: Sampling frequency in Hz
            config: Optional imputation configuration

        Returns:
            ImputationResult with gap-filled data and statistics

        Raises:
            NotImplementedError: If backend doesn't support imputation

        """
        ...

    def compute_epochs(
        self,
        activity_data: np.ndarray,
        timestamps: np.ndarray,
        epoch_length_sec: int,
        sample_rate: float,
    ) -> EpochData:
        """
        Aggregate raw samples into fixed-length epochs.

        Sums absolute values within each epoch window.

        Args:
            activity_data: Activity values (single axis or VM)
            timestamps: Timestamp for each sample
            epoch_length_sec: Length of each epoch in seconds
            sample_rate: Sampling frequency in Hz

        Returns:
            EpochData with aggregated counts and epoch timestamps

        Raises:
            NotImplementedError: If backend doesn't support epoching

        """
        ...

    # ========================
    # Metric Computation Methods
    # ========================

    def compute_enmo(
        self,
        x: np.ndarray,
        y: np.ndarray,
        z: np.ndarray,
    ) -> MetricResult:
        """
        Compute ENMO (Euclidean Norm Minus One) metric.

        ENMO = max(0, sqrt(x^2 + y^2 + z^2) - 1)

        Args:
            x: X-axis acceleration in g
            y: Y-axis acceleration in g
            z: Z-axis acceleration in g

        Returns:
            MetricResult with ENMO values

        Raises:
            NotImplementedError: If backend doesn't support ENMO

        """
        ...

    def compute_angles(
        self,
        x: np.ndarray,
        y: np.ndarray,
        z: np.ndarray,
    ) -> MetricResult:
        """
        Compute arm angles from acceleration vectors.

        Angle-z = atan2(z, sqrt(x^2 + y^2)) * 180/pi

        Args:
            x: X-axis acceleration in g
            y: Y-axis acceleration in g
            z: Z-axis acceleration in g

        Returns:
            MetricResult with angle values in degrees

        Raises:
            NotImplementedError: If backend doesn't support angle computation

        """
        ...

    # ========================
    # Sleep Scoring Methods
    # ========================

    def sadeh_score(
        self,
        activity_counts: np.ndarray,
        variant: str = "actilife",
    ) -> SleepScoreResult:
        """
        Perform Sadeh (1994) sleep scoring.

        Args:
            activity_counts: Activity counts per epoch (60-second)
            variant: Algorithm variant ("original", "actilife", "count_scaled")

        Returns:
            SleepScoreResult with binary sleep/wake scores

        Raises:
            NotImplementedError: If backend doesn't support Sadeh

        """
        ...

    def cole_kripke_score(
        self,
        activity_counts: np.ndarray,
        variant: str = "actilife",
    ) -> SleepScoreResult:
        """
        Perform Cole-Kripke (1992) sleep scoring.

        Args:
            activity_counts: Activity counts per epoch (60-second)
            variant: Algorithm variant ("original", "actilife", "count_scaled")

        Returns:
            SleepScoreResult with binary sleep/wake scores

        Raises:
            NotImplementedError: If backend doesn't support Cole-Kripke

        """
        ...

    def van_hees_sib(
        self,
        angle_z: np.ndarray,
        timestamps: np.ndarray,
        config: dict[str, Any] | None = None,
    ) -> SleepScoreResult:
        """
        Perform Van Hees (2015) sustained inactivity bout detection.

        Args:
            angle_z: Arm angle in degrees
            timestamps: Timestamp for each sample
            config: Optional SIB configuration

        Returns:
            SleepScoreResult with binary sleep/wake scores

        Raises:
            NotImplementedError: If backend doesn't support Van Hees SIB

        """
        ...

    def hdcza_detect(
        self,
        x: np.ndarray,
        y: np.ndarray,
        z: np.ndarray,
        timestamps: np.ndarray,
        config: dict[str, Any] | None = None,
    ) -> SleepDetectionResult:
        """
        Perform HDCZA (2018) sleep detection.

        GGIR's default sleep detection algorithm operating on raw data.

        Args:
            x: X-axis acceleration in g
            y: Y-axis acceleration in g
            z: Z-axis acceleration in g
            timestamps: Timestamp for each sample
            config: Optional HDCZA configuration

        Returns:
            SleepDetectionResult with onset/offset times and metrics

        Raises:
            NotImplementedError: If backend doesn't support HDCZA

        """
        ...

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
        """
        Perform Van Hees nonwear detection (GGIR algorithm).

        Args:
            x: X-axis acceleration in g
            y: Y-axis acceleration in g
            z: Z-axis acceleration in g
            sample_rate: Sampling frequency in Hz
            algorithm: Algorithm version ("2013" or "2023")
            config: Optional nonwear configuration

        Returns:
            NonwearResult with nonwear vector and periods

        Raises:
            NotImplementedError: If backend doesn't support Van Hees nonwear

        """
        ...

    # ========================
    # Circadian Metrics Methods
    # ========================

    def get_m5l5(
        self,
        enmo: np.ndarray,
        timestamps: np.ndarray,
    ) -> CircadianResult:
        """
        Compute M5/L5 circadian rhythm metrics.

        M5 = Most active 5 consecutive hours
        L5 = Least active 5 consecutive hours

        Args:
            enmo: ENMO values
            timestamps: Timestamp for each ENMO value

        Returns:
            CircadianResult with M5, L5, and relative amplitude

        Raises:
            NotImplementedError: If backend doesn't support M5/L5

        """
        ...

    # ========================
    # Validation Methods
    # ========================

    def cohens_kappa(
        self,
        rater1: np.ndarray,
        rater2: np.ndarray,
    ) -> ValidationResult:
        """
        Compute Cohen's kappa inter-rater agreement.

        Args:
            rater1: Binary classifications from rater 1
            rater2: Binary classifications from rater 2

        Returns:
            ValidationResult with kappa value and statistics

        Raises:
            NotImplementedError: If backend doesn't support kappa

        """
        ...
