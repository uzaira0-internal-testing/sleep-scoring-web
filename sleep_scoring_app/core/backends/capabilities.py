"""
Backend capability flags for compute backend abstraction.

This module defines all capabilities that a compute backend might support.
Used by ComputeBackend protocol to declare what operations are available.

Architecture:
    - StrEnum for type-safe capability flags (no magic strings)
    - Enables runtime capability detection
    - Allows backends to declare partial support
    - Used by factory for backend selection

Example Usage:
    >>> from sleep_scoring_app.core.backends import BackendCapability, BackendFactory
    >>>
    >>> # Get backend and check capabilities
    >>> backend = BackendFactory.create()
    >>> if backend.supports(BackendCapability.PARSE_GT3X):
    ...     data = backend.parse_gt3x("file.gt3x")
    >>>
    >>> # Filter backends by capability
    >>> backends = BackendFactory.get_backends_with_capability(BackendCapability.SADEH)

"""

from __future__ import annotations

from enum import StrEnum


class BackendCapability(StrEnum):
    """
    Capability flags for compute backends.

    Each capability represents a specific operation that a backend can perform.
    Backends declare which capabilities they support via the supports() method.

    Categories:
        - Parsing: GT3X file format operations
        - Preprocessing: Calibration, imputation, epoching
        - Metrics: ENMO, angles, filtered metrics
        - Sleep Algorithms: Sadeh, Cole-Kripke, Van Hees, HDCZA
        - Nonwear: Detection algorithms
        - Circadian: M5L5, IS/IV metrics
        - Activity: Classification and bout detection

    """

    # ========================
    # Parsing Capabilities
    # ========================
    PARSE_GT3X = "parse_gt3x"
    """Parse GT3X binary format files to extract accelerometer data"""

    PARSE_GT3X_METADATA = "parse_gt3x_metadata"
    """Extract metadata from GT3X files without loading full data"""

    PARSE_GT3X_SENSORS = "parse_gt3x_sensors"
    """Extract sensor data (lux, battery, capsense, temperature) from GT3X"""

    # ========================
    # Preprocessing Capabilities
    # ========================
    CALIBRATION = "calibration"
    """GGIR-compatible sphere-fitting autocalibration"""

    IMPUTATION = "imputation"
    """GGIR-compatible time gap imputation using row replication"""

    EPOCHING = "epoching"
    """Aggregate raw samples into fixed-length epochs"""

    # ========================
    # Metric Capabilities
    # ========================
    ENMO = "enmo"
    """Compute ENMO (Euclidean Norm Minus One) metric"""

    ANGLES = "angles"
    """Compute arm angles from acceleration vectors"""

    LFENMO = "lfenmo"
    """Compute low-frequency ENMO (filtered metric)"""

    HFEN = "hfen"
    """Compute high-frequency extension (filtered metric)"""

    BFEN = "bfen"
    """Compute band-pass filtered extension (filtered metric)"""

    HFENPLUS = "hfenplus"
    """Compute high-frequency extension plus (enhanced filtered metric)"""

    # ========================
    # Sleep Scoring Capabilities
    # ========================
    SADEH = "sadeh"
    """Sadeh (1994) sleep scoring algorithm"""

    COLE_KRIPKE = "cole_kripke"
    """Cole-Kripke (1992) sleep scoring algorithm"""

    VAN_HEES_SIB = "van_hees_sib"
    """Van Hees (2015) sustained inactivity bout detection"""

    HDCZA = "hdcza"
    """HDCZA (2018) sleep detection algorithm"""

    # ========================
    # Nonwear Detection Capabilities
    # ========================
    VAN_HEES_NONWEAR = "van_hees_nonwear"
    """Van Hees (2013/2023) GGIR nonwear detection"""

    CHOI_NONWEAR = "choi_nonwear"
    """Choi (2011) nonwear detection algorithm"""

    CAPSENSE_NONWEAR = "capsense_nonwear"
    """Capsense hardware-based nonwear detection"""

    # ========================
    # Circadian Metrics Capabilities
    # ========================
    M5L5 = "m5l5"
    """M5/L5 circadian rhythm metrics (most/least active 5h)"""

    IVIS = "ivis"
    """IS/IV circadian variability metrics"""

    SRI = "sri"
    """Sleep Regularity Index calculation"""

    # ========================
    # Activity Classification Capabilities
    # ========================
    ACTIVITY_CLASSIFICATION = "activity_classification"
    """Classify activity levels (sedentary, light, moderate, vigorous)"""

    BOUT_DETECTION = "bout_detection"
    """Detect activity bouts (sustained periods at same level)"""

    FRAGMENTATION = "fragmentation"
    """Calculate fragmentation metrics (transitions, Gini)"""

    # ========================
    # Validation Capabilities
    # ========================
    COHENS_KAPPA = "cohens_kappa"
    """Cohen's kappa inter-rater agreement calculation"""

    ICC = "icc"
    """Intraclass correlation coefficient calculation"""

    BLAND_ALTMAN = "bland_altman"
    """Bland-Altman method comparison analysis"""

    # ========================
    # Batch Processing Capabilities
    # ========================
    PARALLEL_PROCESSING = "parallel_processing"
    """Parallel batch processing of multiple files"""

    STREAMING_PROCESSING = "streaming_processing"
    """Memory-efficient chunked/streaming processing"""
