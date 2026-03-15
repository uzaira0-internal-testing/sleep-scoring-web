"""
Protocol definitions and shared data types for the scoring pipeline.

Each protocol maps to a generalized role in sleep scoring:
- EpochClassifier: per-epoch sleep/wake (GGIR: HASIB)
- BoutDetector: sustained-state detection (GGIR: HASPT)
- PeriodGuider: anchors SPT window search (GGIR: guider)
- PeriodConstructor: assembles final periods (GGIR: SPT-window)
- NonwearDetector: nonwear detection
- DiaryPreprocessor: diary validation/correction
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, Protocol, runtime_checkable

if TYPE_CHECKING:  # pragma: no cover
    from datetime import datetime

    from sleep_scoring_web.schemas.enums import MarkerType

    from .params import (
        BoutDetectorParams,
        DiaryPreprocessorParams,
        EpochClassifierParams,
        NonwearDetectorParams,
        PeriodConstructorParams,
        PeriodGuiderParams,
    )

# =============================================================================
# Shared Data Types
# =============================================================================


@dataclass(frozen=True)
class EpochSeries:
    """Time-aligned epoch data for pipeline processing."""

    timestamps: list[float]
    epoch_times: list[datetime]
    activity_counts: list[float]
    epoch_length_seconds: int = 60

    @property
    def length(self) -> int:
        return len(self.timestamps)


@dataclass(frozen=True)
class ClassifiedEpochs:
    """Per-epoch sleep/wake classification output."""

    scores: list[int]  # 0=wake, 1=sleep
    classifier_id: str = ""


@dataclass(frozen=True)
class Bout:
    """A contiguous run of same-state epochs."""

    start_index: int
    end_index: int  # inclusive
    state: int  # 0=wake, 1=sleep
    length: int = -1  # sentinel; auto-computed if not provided

    def __post_init__(self) -> None:
        if self.length < 0:
            object.__setattr__(self, "length", self.end_index - self.start_index + 1)


@dataclass(frozen=True)
class GuideWindow:
    """Main sleep search anchor from diary or algorithmic guider."""

    onset_target: datetime
    offset_target: datetime
    in_bed_time: datetime | None = None


@dataclass(frozen=True)
class NapGuideWindow:
    """Nap search anchor."""

    start_target: datetime
    end_target: datetime


@dataclass(frozen=True)
class SleepPeriodResult:
    """A detected sleep period (main or nap)."""

    onset_index: int
    offset_index: int
    onset_timestamp: float
    offset_timestamp: float
    period_type: MarkerType
    marker_index: int = 1


@dataclass(frozen=True)
class NonwearPeriodResult:
    """A detected nonwear period."""

    start_index: int
    end_index: int
    start_timestamp: float
    end_timestamp: float
    marker_index: int = 1


@dataclass(frozen=True)
class RawDiaryInput:
    """Raw diary strings as received from the API."""

    bed_time: str | None = None
    onset_time: str | None = None
    wake_time: str | None = None
    naps: list[tuple[str | None, str | None]] = field(default_factory=list)
    nonwear: list[tuple[str | None, str | None]] = field(default_factory=list)
    analysis_date: str | None = None


@dataclass(frozen=True)
class DiaryInput:
    """Preprocessed diary times ready for pipeline use."""

    sleep_onset: datetime | None = None
    wake_time: datetime | None = None
    in_bed_time: datetime | None = None
    nap_periods: list[tuple[datetime, datetime]] = field(default_factory=list)
    nonwear_periods: list[tuple[datetime, datetime]] = field(default_factory=list)


@dataclass
class PipelineResult:
    """Complete pipeline output."""

    sleep_periods: list[SleepPeriodResult] = field(default_factory=list)
    nonwear_periods: list[NonwearPeriodResult] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)

    def to_legacy_dict(self) -> dict[str, Any]:
        """Convert to the dict format expected by existing callers."""
        from sleep_scoring_web.schemas.enums import MarkerType

        sleep_markers: list[dict[str, Any]] = []
        nap_markers: list[dict[str, Any]] = []
        for sp in self.sleep_periods:
            marker = {
                "onset_timestamp": sp.onset_timestamp,
                "offset_timestamp": sp.offset_timestamp,
                "marker_type": sp.period_type,
                "marker_index": sp.marker_index,
            }
            if sp.period_type == MarkerType.NAP:
                nap_markers.append(marker)
            else:
                sleep_markers.append(marker)
        return {
            "sleep_markers": sleep_markers,
            "nap_markers": nap_markers,
            "notes": list(self.notes),
        }


# =============================================================================
# Protocol Definitions
# =============================================================================


@runtime_checkable
class EpochClassifier(Protocol):  # pragma: no cover
    """Per-epoch sleep/wake classification. GGIR equivalent: HASIB."""

    @property
    def id(self) -> str: ...

    def classify(
        self,
        epochs: EpochSeries,
        *,
        params: EpochClassifierParams | None = None,
    ) -> ClassifiedEpochs: ...


@runtime_checkable
class BoutDetector(Protocol):  # pragma: no cover
    """Sustained-state bout detection. GGIR equivalent: HASPT."""

    @property
    def id(self) -> str: ...

    def detect_bouts(
        self,
        classified: ClassifiedEpochs,
        *,
        params: BoutDetectorParams | None = None,
    ) -> list[Bout]: ...


@runtime_checkable
class PeriodGuider(Protocol):  # pragma: no cover
    """Anchors SPT window search. GGIR equivalent: guider (diary/HDCZA/L5+6)."""

    @property
    def id(self) -> str: ...

    def guide(
        self,
        epochs: EpochSeries,
        classified: ClassifiedEpochs,
        bouts: list[Bout],
        *,
        params: PeriodGuiderParams | None = None,
        diary_data: DiaryInput | None = None,
    ) -> tuple[GuideWindow | None, list[NapGuideWindow], list[str]]: ...


@runtime_checkable
class PeriodConstructor(Protocol):  # pragma: no cover
    """Assembles final sleep periods. GGIR equivalent: SPT-window construction."""

    @property
    def id(self) -> str: ...

    def construct(
        self,
        epochs: EpochSeries,
        classified: ClassifiedEpochs,
        bouts: list[Bout],
        main_guide: GuideWindow | None,
        nap_guides: list[NapGuideWindow],
        *,
        params: PeriodConstructorParams | None = None,
    ) -> list[SleepPeriodResult]: ...


@runtime_checkable
class NonwearDetector(Protocol):  # pragma: no cover
    """Nonwear period detection."""

    @property
    def id(self) -> str: ...

    def detect(
        self,
        epochs: EpochSeries,
        *,
        params: NonwearDetectorParams | None = None,
        diary_data: DiaryInput | None = None,
        existing_sleep: list[SleepPeriodResult] | None = None,
    ) -> list[NonwearPeriodResult]: ...


@runtime_checkable
class DiaryPreprocessor(Protocol):  # pragma: no cover
    """Validates/corrects diary inputs."""

    @property
    def id(self) -> str: ...

    def preprocess(
        self,
        raw_diary: RawDiaryInput,
        data_window: tuple[float, float],
        *,
        params: DiaryPreprocessorParams | None = None,
    ) -> tuple[DiaryInput, list[str]]: ...
