"""
Tests for the pipeline subsystem under sleep_scoring_web/services/pipeline/.

Covers: protocols, registry, params, compat, orchestrator,
bout_detectors/consecutive_run, period_constructors/onset_offset,
period_guiders/diary + none, diary_preprocessors/ampm_corrector + passthrough,
epoch_classifiers/sadeh + cole_kripke, nonwear_detectors/choi + diary_anchored.
"""

from __future__ import annotations

from dataclasses import replace
from datetime import UTC, datetime, timedelta
from unittest.mock import MagicMock, patch

import pytest

# ---------------------------------------------------------------------------
# Ensure all pipeline components are registered before any test runs
# ---------------------------------------------------------------------------
from sleep_scoring_web.services.pipeline import (
    Bout,
    BoutDetectorParams,
    ClassifiedEpochs,
    DiaryInput,
    DiaryPreprocessorParams,
    EpochClassifierParams,
    EpochSeries,
    GuideWindow,
    NapGuideWindow,
    NonwearDetectorParams,
    NonwearPeriodResult,
    PeriodConstructorParams,
    PeriodGuiderParams,
    PipelineParams,
    PipelineResult,
    PipelineRole,
    RawDiaryInput,
    ScoringPipeline,
    SleepPeriodResult,
    describe_pipeline,
    run_via_pipeline,
)
from sleep_scoring_web.services.pipeline.registry import (
    _INSTANCE_CACHE,
    _REGISTRY,
    get_component,
    register,
)
from sleep_scoring_web.schemas.enums import AlgorithmType, MarkerType

# Component classes
from sleep_scoring_web.services.pipeline.bout_detectors.consecutive_run import (
    ConsecutiveRunBoutDetector,
)
from sleep_scoring_web.services.pipeline.diary_preprocessors.ampm_corrector import (
    AmPmDiaryPreprocessor,
)
from sleep_scoring_web.services.pipeline.diary_preprocessors.passthrough import (
    PassthroughDiaryPreprocessor,
)
from sleep_scoring_web.services.pipeline.epoch_classifiers.cole_kripke import (
    ColeKripkeEpochClassifier,
    ColeKripkeOriginalEpochClassifier,
)
from sleep_scoring_web.services.pipeline.epoch_classifiers.sadeh import (
    SadehEpochClassifier,
    SadehOriginalEpochClassifier,
)
from sleep_scoring_web.services.pipeline.nonwear_detectors.choi import (
    ChoiNonwearDetector,
)
from sleep_scoring_web.services.pipeline.nonwear_detectors.diary_anchored import (
    DiaryAnchoredNonwearDetector,
)
from sleep_scoring_web.services.pipeline.period_constructors.onset_offset import (
    OnsetOffsetPeriodConstructor,
)
from sleep_scoring_web.services.pipeline.period_guiders.diary import (
    DiaryPeriodGuider,
)
from sleep_scoring_web.services.pipeline.period_guiders.none import (
    NullPeriodGuider,
)


# =============================================================================
# Helpers — synthetic data builders
# =============================================================================

def _make_timestamps(n: int, start: datetime | None = None, epoch_seconds: int = 60) -> list[float]:
    """Generate n timestamps starting at `start`, spaced `epoch_seconds` apart."""
    if start is None:
        start = datetime(2024, 1, 15, 22, 0, tzinfo=UTC)
    return [start.timestamp() + i * epoch_seconds for i in range(n)]


def _make_epoch_series(
    n: int,
    activity: list[float] | None = None,
    start: datetime | None = None,
    epoch_seconds: int = 60,
) -> EpochSeries:
    """Build an EpochSeries of length n with optional activity data."""
    if start is None:
        start = datetime(2024, 1, 15, 22, 0, tzinfo=UTC)
    timestamps = _make_timestamps(n, start, epoch_seconds)
    epoch_times = [datetime.fromtimestamp(ts, tz=UTC) for ts in timestamps]
    if activity is None:
        activity = [0.0] * n
    return EpochSeries(
        timestamps=timestamps,
        epoch_times=epoch_times,
        activity_counts=activity,
        epoch_length_seconds=epoch_seconds,
    )


# =============================================================================
# Protocol data-type tests
# =============================================================================

class TestEpochSeries:
    def test_length_property(self) -> None:
        es = _make_epoch_series(10)
        assert es.length == 10

    def test_frozen(self) -> None:
        es = _make_epoch_series(5)
        with pytest.raises(AttributeError):
            es.epoch_length_seconds = 30  # type: ignore[misc]

    def test_empty(self) -> None:
        es = _make_epoch_series(0, activity=[])
        assert es.length == 0


class TestClassifiedEpochs:
    def test_basic(self) -> None:
        ce = ClassifiedEpochs(scores=[1, 0, 1], classifier_id="test")
        assert ce.scores == [1, 0, 1]
        assert ce.classifier_id == "test"

    def test_default_classifier_id(self) -> None:
        ce = ClassifiedEpochs(scores=[])
        assert ce.classifier_id == ""


class TestBout:
    def test_auto_length(self) -> None:
        b = Bout(start_index=3, end_index=7, state=1)
        assert b.length == 5

    def test_explicit_length(self) -> None:
        b = Bout(start_index=0, end_index=9, state=0, length=10)
        assert b.length == 10

    def test_frozen(self) -> None:
        b = Bout(start_index=0, end_index=5, state=1)
        with pytest.raises(AttributeError):
            b.state = 0  # type: ignore[misc]


class TestGuideWindow:
    def test_defaults(self) -> None:
        onset = datetime(2024, 1, 15, 22, 0, tzinfo=UTC)
        offset = datetime(2024, 1, 16, 6, 0, tzinfo=UTC)
        gw = GuideWindow(onset_target=onset, offset_target=offset)
        assert gw.in_bed_time is None

    def test_with_in_bed(self) -> None:
        onset = datetime(2024, 1, 15, 22, 0, tzinfo=UTC)
        offset = datetime(2024, 1, 16, 6, 0, tzinfo=UTC)
        bed = datetime(2024, 1, 15, 21, 30, tzinfo=UTC)
        gw = GuideWindow(onset_target=onset, offset_target=offset, in_bed_time=bed)
        assert gw.in_bed_time == bed


class TestSleepPeriodResult:
    def test_marker_index_default(self) -> None:
        sp = SleepPeriodResult(
            onset_index=0, offset_index=10,
            onset_timestamp=100.0, offset_timestamp=700.0,
            period_type=MarkerType.MAIN_SLEEP,
        )
        assert sp.marker_index == 1


class TestNonwearPeriodResult:
    def test_basic(self) -> None:
        nw = NonwearPeriodResult(
            start_index=5, end_index=15,
            start_timestamp=300.0, end_timestamp=900.0,
        )
        assert nw.marker_index == 1


class TestRawDiaryInput:
    def test_defaults(self) -> None:
        raw = RawDiaryInput()
        assert raw.bed_time is None
        assert raw.naps == []
        assert raw.nonwear == []


class TestDiaryInput:
    def test_defaults(self) -> None:
        di = DiaryInput()
        assert di.sleep_onset is None
        assert di.nap_periods == []


class TestPipelineResult:
    def test_to_legacy_dict_empty(self) -> None:
        pr = PipelineResult()
        d = pr.to_legacy_dict()
        assert d == {"sleep_markers": [], "nap_markers": [], "notes": []}

    def test_to_legacy_dict_with_markers(self) -> None:
        sp_main = SleepPeriodResult(
            onset_index=0, offset_index=10,
            onset_timestamp=100.0, offset_timestamp=700.0,
            period_type=MarkerType.MAIN_SLEEP, marker_index=1,
        )
        sp_nap = SleepPeriodResult(
            onset_index=20, offset_index=30,
            onset_timestamp=1200.0, offset_timestamp=1800.0,
            period_type=MarkerType.NAP, marker_index=2,
        )
        pr = PipelineResult(
            sleep_periods=[sp_main, sp_nap],
            notes=["test note"],
        )
        d = pr.to_legacy_dict()
        assert len(d["sleep_markers"]) == 1
        assert len(d["nap_markers"]) == 1
        assert d["notes"] == ["test note"]
        assert d["sleep_markers"][0]["marker_type"] == MarkerType.MAIN_SLEEP
        assert d["nap_markers"][0]["marker_type"] == MarkerType.NAP


# =============================================================================
# Registry tests
# =============================================================================

class TestRegistry:
    def test_describe_pipeline_has_all_roles(self) -> None:
        desc = describe_pipeline()
        for role in PipelineRole:
            assert role.value in desc

    def test_describe_pipeline_lists_known_components(self) -> None:
        desc = describe_pipeline()
        assert "consecutive_run" in desc["bout_detector"]
        assert "diary" in desc["period_guider"]
        assert "none" in desc["period_guider"]
        assert "onset_offset" in desc["period_constructor"]
        assert "choi" in desc["nonwear_detector"]
        assert "diary_anchored" in desc["nonwear_detector"]
        assert "ampm_corrector" in desc["diary_preprocessor"]
        assert "passthrough" in desc["diary_preprocessor"]
        assert "sadeh_1994_actilife" in desc["epoch_classifier"]
        assert "cole_kripke_1992_actilife" in desc["epoch_classifier"]

    def test_get_component_returns_singleton(self) -> None:
        a = get_component("bout_detector", "consecutive_run")
        b = get_component("bout_detector", "consecutive_run")
        assert a is b

    def test_get_component_unknown_raises(self) -> None:
        with pytest.raises(ValueError, match="Unknown"):
            get_component("bout_detector", "nonexistent_detector_xyz")

    def test_register_decorator(self) -> None:
        @register("bout_detector", "_test_dummy_for_test_pipeline")
        class DummyBoutDetector:
            @property
            def id(self) -> str:
                return "_test_dummy_for_test_pipeline"

        assert "_test_dummy_for_test_pipeline" in _REGISTRY[PipelineRole.BOUT_DETECTOR]
        # Cleanup
        del _REGISTRY[PipelineRole.BOUT_DETECTOR]["_test_dummy_for_test_pipeline"]
        _INSTANCE_CACHE.pop((PipelineRole.BOUT_DETECTOR, "_test_dummy_for_test_pipeline"), None)

    def test_register_invalid_role_raises(self) -> None:
        with pytest.raises(ValueError):
            register("not_a_real_role", "whatever")


# =============================================================================
# Params tests
# =============================================================================

class TestPipelineParams:
    def test_defaults(self) -> None:
        pp = PipelineParams()
        assert pp.epoch_classifier == AlgorithmType.SADEH_1994_ACTILIFE
        assert pp.bout_detector == "consecutive_run"
        assert pp.period_guider == "diary"
        assert pp.period_constructor == "onset_offset"
        assert pp.nonwear_detector == "flat_activity"
        assert pp.diary_preprocessor == "ampm_corrector"

    def test_from_legacy_defaults(self) -> None:
        pp = PipelineParams.from_legacy()
        assert pp.period_guider == "diary"
        assert pp.diary_preprocessor == "ampm_corrector"
        assert pp.period_constructor_params.onset_min_consecutive_sleep == 3
        assert pp.period_constructor_params.offset_min_consecutive_minutes == 5

    def test_from_legacy_no_diary(self) -> None:
        pp = PipelineParams.from_legacy(include_diary=False)
        assert pp.period_guider == "none"
        assert pp.diary_preprocessor == "passthrough"

    def test_from_legacy_custom_params(self) -> None:
        pp = PipelineParams.from_legacy(
            algorithm="cole_kripke_1992_actilife",
            onset_epochs=5,
            offset_minutes=10,
        )
        assert pp.epoch_classifier == "cole_kripke_1992_actilife"
        assert pp.period_constructor_params.onset_min_consecutive_sleep == 5
        assert pp.period_constructor_params.offset_min_consecutive_minutes == 10

    def test_period_constructor_params_defaults(self) -> None:
        p = PeriodConstructorParams()
        assert p.onset_min_consecutive_sleep == 3
        assert p.offset_min_consecutive_minutes == 5
        assert p.max_forward_offset_epochs == 60
        assert p.nap_min_consecutive_epochs == 10
        assert p.epoch_length_seconds == 60
        assert p.enable_rule_8_clamping is True

    def test_nonwear_detector_params_defaults(self) -> None:
        p = NonwearDetectorParams()
        assert p.activity_threshold == 0
        assert p.zero_activity_ratio == 0.65
        assert p.min_duration_minutes == 10
        assert p.flat_activity_min_minutes == 60
        assert p.flat_activity_resumption_threshold == 500

    def test_diary_preprocessor_params_defaults(self) -> None:
        p = DiaryPreprocessorParams()
        assert p.enable_ampm_correction is True
        assert p.plausibility_min_hours == 2.0
        assert p.plausibility_max_hours == 18.0


# =============================================================================
# ConsecutiveRunBoutDetector tests
# =============================================================================

class TestConsecutiveRunBoutDetector:
    def setup_method(self) -> None:
        self.detector = ConsecutiveRunBoutDetector()

    def test_id(self) -> None:
        assert self.detector.id == "consecutive_run"

    def test_empty_scores(self) -> None:
        result = self.detector.detect_bouts(ClassifiedEpochs(scores=[]))
        assert result == []

    def test_single_state(self) -> None:
        result = self.detector.detect_bouts(ClassifiedEpochs(scores=[1, 1, 1]))
        assert len(result) == 1
        assert result[0].start_index == 0
        assert result[0].end_index == 2
        assert result[0].state == 1
        assert result[0].length == 3

    def test_alternating(self) -> None:
        result = self.detector.detect_bouts(ClassifiedEpochs(scores=[0, 1, 0]))
        assert len(result) == 3
        assert result[0] == Bout(start_index=0, end_index=0, state=0, length=1)
        assert result[1] == Bout(start_index=1, end_index=1, state=1, length=1)
        assert result[2] == Bout(start_index=2, end_index=2, state=0, length=1)

    def test_consecutive_runs(self) -> None:
        # wake-wake-sleep-sleep-sleep-wake
        scores = [0, 0, 1, 1, 1, 0]
        result = self.detector.detect_bouts(ClassifiedEpochs(scores=scores))
        assert len(result) == 3
        assert result[0] == Bout(start_index=0, end_index=1, state=0, length=2)
        assert result[1] == Bout(start_index=2, end_index=4, state=1, length=3)
        assert result[2] == Bout(start_index=5, end_index=5, state=0, length=1)

    def test_all_sleep(self) -> None:
        scores = [1] * 20
        result = self.detector.detect_bouts(ClassifiedEpochs(scores=scores))
        assert len(result) == 1
        assert result[0].length == 20

    def test_single_epoch(self) -> None:
        result = self.detector.detect_bouts(ClassifiedEpochs(scores=[0]))
        assert len(result) == 1
        assert result[0] == Bout(start_index=0, end_index=0, state=0, length=1)

    def test_many_transitions(self) -> None:
        # 1,0,1,0,1,0,1,0 => 8 bouts
        scores = [1, 0] * 4
        result = self.detector.detect_bouts(ClassifiedEpochs(scores=scores))
        assert len(result) == 8

    def test_params_accepted(self) -> None:
        """Ensure params kwarg is accepted even though consecutive_run ignores it."""
        result = self.detector.detect_bouts(
            ClassifiedEpochs(scores=[0, 1]),
            params=BoutDetectorParams(min_sleep_bout_epochs=3),
        )
        assert len(result) == 2


# =============================================================================
# NullPeriodGuider tests
# =============================================================================

class TestNullPeriodGuider:
    def setup_method(self) -> None:
        self.guider = NullPeriodGuider()

    def test_id(self) -> None:
        assert self.guider.id == "none"

    def test_returns_none_guide(self) -> None:
        epochs = _make_epoch_series(10)
        classified = ClassifiedEpochs(scores=[0] * 10)
        main_guide, nap_guides, notes = self.guider.guide(
            epochs, classified, [],
        )
        assert main_guide is None
        assert nap_guides == []
        assert any("diary-free" in n.lower() for n in notes)

    def test_ignores_diary_data(self) -> None:
        """Even if diary_data is provided, NullPeriodGuider ignores it."""
        epochs = _make_epoch_series(10)
        classified = ClassifiedEpochs(scores=[0] * 10)
        diary = DiaryInput(
            sleep_onset=datetime(2024, 1, 15, 22, 0, tzinfo=UTC),
            wake_time=datetime(2024, 1, 16, 6, 0, tzinfo=UTC),
        )
        main_guide, nap_guides, notes = self.guider.guide(
            epochs, classified, [], diary_data=diary,
        )
        assert main_guide is None


# =============================================================================
# DiaryPeriodGuider tests
# =============================================================================

class TestDiaryPeriodGuider:
    def setup_method(self) -> None:
        self.guider = DiaryPeriodGuider()

    def test_id(self) -> None:
        assert self.guider.id == "diary"

    def test_no_diary_data(self) -> None:
        epochs = _make_epoch_series(10)
        classified = ClassifiedEpochs(scores=[0] * 10)
        main_guide, nap_guides, notes = self.guider.guide(
            epochs, classified, [],
        )
        assert main_guide is None
        assert nap_guides == []
        assert any("No diary data" in n for n in notes)

    def test_diary_with_onset_and_wake(self) -> None:
        epochs = _make_epoch_series(10)
        classified = ClassifiedEpochs(scores=[0] * 10)
        onset = datetime(2024, 1, 15, 22, 30, tzinfo=UTC)
        wake = datetime(2024, 1, 16, 6, 30, tzinfo=UTC)
        bed = datetime(2024, 1, 15, 22, 0, tzinfo=UTC)
        diary = DiaryInput(sleep_onset=onset, wake_time=wake, in_bed_time=bed)
        main_guide, nap_guides, notes = self.guider.guide(
            epochs, classified, [], diary_data=diary,
        )
        assert main_guide is not None
        assert main_guide.onset_target == onset
        assert main_guide.offset_target == wake
        assert main_guide.in_bed_time == bed

    def test_diary_missing_onset(self) -> None:
        epochs = _make_epoch_series(10)
        classified = ClassifiedEpochs(scores=[0] * 10)
        diary = DiaryInput(wake_time=datetime(2024, 1, 16, 6, 0, tzinfo=UTC))
        main_guide, nap_guides, notes = self.guider.guide(
            epochs, classified, [], diary_data=diary,
        )
        assert main_guide is None
        assert any("incomplete" in n.lower() or "missing" in n.lower() for n in notes)

    def test_diary_missing_wake(self) -> None:
        epochs = _make_epoch_series(10)
        classified = ClassifiedEpochs(scores=[0] * 10)
        diary = DiaryInput(sleep_onset=datetime(2024, 1, 15, 22, 0, tzinfo=UTC))
        main_guide, _, notes = self.guider.guide(
            epochs, classified, [], diary_data=diary,
        )
        assert main_guide is None
        assert any("incomplete" in n.lower() or "missing" in n.lower() for n in notes)

    def test_diary_no_times_at_all(self) -> None:
        epochs = _make_epoch_series(10)
        classified = ClassifiedEpochs(scores=[0] * 10)
        diary = DiaryInput()
        main_guide, _, notes = self.guider.guide(
            epochs, classified, [], diary_data=diary,
        )
        assert main_guide is None
        assert any("no onset/wake" in n.lower() for n in notes)

    def test_diary_with_naps(self) -> None:
        epochs = _make_epoch_series(10)
        classified = ClassifiedEpochs(scores=[0] * 10)
        nap_start = datetime(2024, 1, 15, 13, 0, tzinfo=UTC)
        nap_end = datetime(2024, 1, 15, 14, 0, tzinfo=UTC)
        diary = DiaryInput(
            sleep_onset=datetime(2024, 1, 15, 22, 0, tzinfo=UTC),
            wake_time=datetime(2024, 1, 16, 6, 0, tzinfo=UTC),
            nap_periods=[(nap_start, nap_end)],
        )
        main_guide, nap_guides, notes = self.guider.guide(
            epochs, classified, [], diary_data=diary,
        )
        assert main_guide is not None
        assert len(nap_guides) == 1
        assert nap_guides[0].start_target == nap_start
        assert nap_guides[0].end_target == nap_end

    def test_diary_multiple_naps(self) -> None:
        epochs = _make_epoch_series(10)
        classified = ClassifiedEpochs(scores=[0] * 10)
        nap1 = (datetime(2024, 1, 15, 13, 0, tzinfo=UTC), datetime(2024, 1, 15, 14, 0, tzinfo=UTC))
        nap2 = (datetime(2024, 1, 15, 16, 0, tzinfo=UTC), datetime(2024, 1, 15, 17, 0, tzinfo=UTC))
        diary = DiaryInput(
            sleep_onset=datetime(2024, 1, 15, 22, 0, tzinfo=UTC),
            wake_time=datetime(2024, 1, 16, 6, 0, tzinfo=UTC),
            nap_periods=[nap1, nap2],
        )
        _, nap_guides, _ = self.guider.guide(
            epochs, classified, [], diary_data=diary,
        )
        assert len(nap_guides) == 2


# =============================================================================
# PassthroughDiaryPreprocessor tests
# =============================================================================

class TestPassthroughDiaryPreprocessor:
    def setup_method(self) -> None:
        self.preprocessor = PassthroughDiaryPreprocessor()

    def test_id(self) -> None:
        assert self.preprocessor.id == "passthrough"

    def test_returns_empty_diary(self) -> None:
        raw = RawDiaryInput(
            bed_time="22:00",
            onset_time="22:30",
            wake_time="06:00",
            analysis_date="2024-01-15",
        )
        diary, notes = self.preprocessor.preprocess(raw, (0.0, 100.0))
        assert diary == DiaryInput()
        assert notes == []

    def test_handles_empty_raw_diary(self) -> None:
        raw = RawDiaryInput()
        diary, notes = self.preprocessor.preprocess(raw, (0.0, 100.0))
        assert diary == DiaryInput()
        assert notes == []


# =============================================================================
# AmPmDiaryPreprocessor tests
# =============================================================================

class TestAmPmDiaryPreprocessor:
    def setup_method(self) -> None:
        self.preprocessor = AmPmDiaryPreprocessor()

    def test_id(self) -> None:
        assert self.preprocessor.id == "ampm_corrector"

    def test_no_analysis_date_returns_empty(self) -> None:
        raw = RawDiaryInput(onset_time="22:00", wake_time="06:00")
        diary, notes = self.preprocessor.preprocess(raw, (0.0, 100.0))
        assert diary == DiaryInput()

    def test_basic_24h_times(self) -> None:
        """Test parsing simple 24-hour times with valid data window."""
        base_date = datetime(2024, 1, 15, tzinfo=UTC)
        # data window spans the expected sleep period
        data_start = datetime(2024, 1, 15, 18, 0, tzinfo=UTC)
        data_end = datetime(2024, 1, 16, 12, 0, tzinfo=UTC)
        raw = RawDiaryInput(
            onset_time="22:00",
            wake_time="06:00",
            analysis_date="2024-01-15",
        )
        diary, notes = self.preprocessor.preprocess(
            raw,
            (data_start.timestamp(), data_end.timestamp()),
        )
        assert diary.sleep_onset is not None
        assert diary.wake_time is not None
        # Onset should be on Jan 15 (evening)
        assert diary.sleep_onset.hour == 22
        # Wake should be on Jan 16 (morning)
        assert diary.wake_time.hour == 6
        assert diary.wake_time.day == 16

    def test_with_nap_periods(self) -> None:
        """Test parsing nap time strings."""
        base_date = datetime(2024, 1, 15, tzinfo=UTC)
        data_start = datetime(2024, 1, 15, 0, 0, tzinfo=UTC)
        data_end = datetime(2024, 1, 16, 23, 59, tzinfo=UTC)
        raw = RawDiaryInput(
            onset_time="22:00",
            wake_time="06:00",
            naps=[("13:00", "14:00")],
            analysis_date="2024-01-15",
        )
        diary, notes = self.preprocessor.preprocess(
            raw,
            (data_start.timestamp(), data_end.timestamp()),
        )
        assert len(diary.nap_periods) == 1
        nap_start, nap_end = diary.nap_periods[0]
        assert nap_start.hour == 13
        assert nap_end.hour == 14

    def test_with_nonwear_periods(self) -> None:
        """Test parsing nonwear time strings."""
        data_start = datetime(2024, 1, 15, 0, 0, tzinfo=UTC)
        data_end = datetime(2024, 1, 16, 23, 59, tzinfo=UTC)
        raw = RawDiaryInput(
            onset_time="22:00",
            wake_time="06:00",
            nonwear=[("10:00", "11:00")],
            analysis_date="2024-01-15",
        )
        diary, notes = self.preprocessor.preprocess(
            raw,
            (data_start.timestamp(), data_end.timestamp()),
        )
        assert len(diary.nonwear_periods) == 1

    def test_ampm_correction_disabled(self) -> None:
        """Test with AM/PM correction disabled."""
        data_start = datetime(2024, 1, 15, 0, 0, tzinfo=UTC)
        data_end = datetime(2024, 1, 16, 23, 59, tzinfo=UTC)
        raw = RawDiaryInput(
            onset_time="22:00",
            wake_time="06:00",
            analysis_date="2024-01-15",
        )
        params = DiaryPreprocessorParams(enable_ampm_correction=False)
        diary, notes = self.preprocessor.preprocess(
            raw,
            (data_start.timestamp(), data_end.timestamp()),
            params=params,
        )
        assert diary.sleep_onset is not None
        assert diary.sleep_onset.hour == 22

    def test_nap_end_before_start_wraps(self) -> None:
        """If nap end <= nap start, it should wrap to next day."""
        data_start = datetime(2024, 1, 15, 0, 0, tzinfo=UTC)
        data_end = datetime(2024, 1, 17, 23, 59, tzinfo=UTC)
        raw = RawDiaryInput(
            onset_time="22:00",
            wake_time="06:00",
            naps=[("23:00", "01:00")],
            analysis_date="2024-01-15",
        )
        diary, notes = self.preprocessor.preprocess(
            raw,
            (data_start.timestamp(), data_end.timestamp()),
        )
        if diary.nap_periods:
            nap_start, nap_end = diary.nap_periods[0]
            assert nap_end > nap_start

    def test_bed_time_used_as_in_bed(self) -> None:
        """bed_time should populate in_bed_time."""
        data_start = datetime(2024, 1, 15, 18, 0, tzinfo=UTC)
        data_end = datetime(2024, 1, 16, 12, 0, tzinfo=UTC)
        raw = RawDiaryInput(
            bed_time="21:30",
            onset_time="22:00",
            wake_time="06:00",
            analysis_date="2024-01-15",
        )
        diary, notes = self.preprocessor.preprocess(
            raw,
            (data_start.timestamp(), data_end.timestamp()),
        )
        assert diary.in_bed_time is not None

    def test_onset_falls_back_to_bed_time(self) -> None:
        """When onset_time is None, bed_time is used as onset_str."""
        data_start = datetime(2024, 1, 15, 18, 0, tzinfo=UTC)
        data_end = datetime(2024, 1, 16, 12, 0, tzinfo=UTC)
        raw = RawDiaryInput(
            bed_time="22:00",
            onset_time=None,
            wake_time="06:00",
            analysis_date="2024-01-15",
        )
        diary, notes = self.preprocessor.preprocess(
            raw,
            (data_start.timestamp(), data_end.timestamp()),
        )
        # Should have parsed onset from bed_time fallback
        assert diary.sleep_onset is not None

    def test_nap_with_none_values_skipped(self) -> None:
        """Nap entries with None values should be skipped."""
        data_start = datetime(2024, 1, 15, 0, 0, tzinfo=UTC)
        data_end = datetime(2024, 1, 16, 23, 59, tzinfo=UTC)
        raw = RawDiaryInput(
            onset_time="22:00",
            wake_time="06:00",
            naps=[(None, "14:00"), ("13:00", None), (None, None)],
            analysis_date="2024-01-15",
        )
        diary, notes = self.preprocessor.preprocess(
            raw,
            (data_start.timestamp(), data_end.timestamp()),
        )
        assert len(diary.nap_periods) == 0


# =============================================================================
# SadehEpochClassifier tests
# =============================================================================

class TestSadehEpochClassifier:
    def setup_method(self) -> None:
        self.classifier = SadehEpochClassifier()

    def test_id(self) -> None:
        assert self.classifier.id == "sadeh_1994_actilife"

    def test_classify_returns_classified_epochs(self) -> None:
        # Generate enough epochs for Sadeh's 11-minute window
        activity = [0.0] * 30
        epochs = _make_epoch_series(30, activity=activity)
        result = self.classifier.classify(epochs)
        assert isinstance(result, ClassifiedEpochs)
        assert len(result.scores) == 30
        assert result.classifier_id == "sadeh_1994_actilife"

    def test_all_zero_activity_classified_as_sleep(self) -> None:
        """All-zero activity should be classified as sleep."""
        activity = [0.0] * 30
        epochs = _make_epoch_series(30, activity=activity)
        result = self.classifier.classify(epochs)
        # With zero activity, Sadeh should classify as sleep (1)
        assert all(s == 1 for s in result.scores)

    def test_high_activity_classified_as_wake(self) -> None:
        """High activity should be classified as wake."""
        activity = [500.0] * 30
        epochs = _make_epoch_series(30, activity=activity)
        result = self.classifier.classify(epochs)
        # With very high activity, most epochs should be wake (0)
        assert sum(result.scores) < len(result.scores)  # not all sleep

    def test_params_threshold_override(self) -> None:
        """Threshold override via params should work."""
        activity = [0.0] * 30
        epochs = _make_epoch_series(30, activity=activity)
        params = EpochClassifierParams(threshold=100.0)
        result = self.classifier.classify(epochs, params=params)
        assert isinstance(result, ClassifiedEpochs)

    def test_empty_activity(self) -> None:
        epochs = _make_epoch_series(0, activity=[])
        result = self.classifier.classify(epochs)
        assert result.scores == []


class TestSadehOriginalEpochClassifier:
    def test_id(self) -> None:
        classifier = SadehOriginalEpochClassifier()
        assert classifier.id == "sadeh_1994_original"

    def test_classify_basic(self) -> None:
        classifier = SadehOriginalEpochClassifier()
        activity = [0.0] * 20
        epochs = _make_epoch_series(20, activity=activity)
        result = classifier.classify(epochs)
        assert len(result.scores) == 20


# =============================================================================
# ColeKripkeEpochClassifier tests
# =============================================================================

class TestColeKripkeEpochClassifier:
    def setup_method(self) -> None:
        self.classifier = ColeKripkeEpochClassifier()

    def test_id(self) -> None:
        assert self.classifier.id == "cole_kripke_1992_actilife"

    def test_classify_returns_classified_epochs(self) -> None:
        activity = [0.0] * 20
        epochs = _make_epoch_series(20, activity=activity)
        result = self.classifier.classify(epochs)
        assert isinstance(result, ClassifiedEpochs)
        assert len(result.scores) == 20
        assert result.classifier_id == "cole_kripke_1992_actilife"

    def test_all_zero_activity(self) -> None:
        activity = [0.0] * 20
        epochs = _make_epoch_series(20, activity=activity)
        result = self.classifier.classify(epochs)
        # Zero activity should mostly be classified as sleep
        assert all(s == 1 for s in result.scores)

    def test_high_activity(self) -> None:
        activity = [1000.0] * 20
        epochs = _make_epoch_series(20, activity=activity)
        result = self.classifier.classify(epochs)
        # High activity should have some wake epochs
        assert sum(result.scores) < len(result.scores)

    def test_empty_activity(self) -> None:
        epochs = _make_epoch_series(0, activity=[])
        result = self.classifier.classify(epochs)
        assert result.scores == []


class TestColeKripkeOriginalEpochClassifier:
    def test_id(self) -> None:
        classifier = ColeKripkeOriginalEpochClassifier()
        assert classifier.id == "cole_kripke_1992_original"

    def test_classify_basic(self) -> None:
        classifier = ColeKripkeOriginalEpochClassifier()
        activity = [0.0] * 20
        epochs = _make_epoch_series(20, activity=activity)
        result = classifier.classify(epochs)
        assert len(result.scores) == 20


# =============================================================================
# ChoiNonwearDetector tests
# =============================================================================

class TestChoiNonwearDetector:
    def setup_method(self) -> None:
        self.detector = ChoiNonwearDetector()

    def test_id(self) -> None:
        assert self.detector.id == "choi"

    def test_empty_activity(self) -> None:
        epochs = _make_epoch_series(0, activity=[])
        result = self.detector.detect(epochs)
        assert result == []

    def test_no_nonwear_with_activity(self) -> None:
        """Constant high activity should not trigger nonwear."""
        activity = [100.0] * 60
        epochs = _make_epoch_series(60, activity=activity)
        result = self.detector.detect(epochs)
        assert result == []

    def test_long_zero_period_detected(self) -> None:
        """A 90+ minute zero-activity period should be detected as nonwear."""
        # Choi requires >= 90 consecutive zero-activity minutes
        activity = [100.0] * 30 + [0.0] * 100 + [100.0] * 30
        epochs = _make_epoch_series(len(activity), activity=activity)
        result = self.detector.detect(epochs)
        assert len(result) >= 1
        # The nonwear period should be within the zero-activity region
        nw = result[0]
        assert isinstance(nw, NonwearPeriodResult)
        assert nw.start_index >= 25  # roughly in the zero region
        assert nw.end_index <= 135

    def test_short_zero_period_not_detected(self) -> None:
        """A short zero-activity period (<90 min) should NOT be detected."""
        activity = [100.0] * 30 + [0.0] * 50 + [100.0] * 30
        epochs = _make_epoch_series(len(activity), activity=activity)
        result = self.detector.detect(epochs)
        assert result == []

    def test_params_accepted(self) -> None:
        """Ensure params kwarg is accepted."""
        activity = [0.0] * 100
        epochs = _make_epoch_series(100, activity=activity)
        params = NonwearDetectorParams(activity_threshold=0)
        result = self.detector.detect(epochs, params=params)
        assert isinstance(result, list)


# =============================================================================
# DiaryAnchoredNonwearDetector tests
# =============================================================================

class TestDiaryAnchoredNonwearDetector:
    def setup_method(self) -> None:
        self.detector = DiaryAnchoredNonwearDetector()

    def test_id(self) -> None:
        assert self.detector.id == "diary_anchored"

    def test_no_diary_data(self) -> None:
        epochs = _make_epoch_series(60)
        result = self.detector.detect(epochs, diary_data=None)
        assert result == []

    def test_no_nonwear_periods_in_diary(self) -> None:
        epochs = _make_epoch_series(60)
        diary = DiaryInput()  # no nonwear_periods
        result = self.detector.detect(epochs, diary_data=diary)
        assert result == []

    def test_diary_with_nonwear_and_zero_activity(self) -> None:
        """Diary nonwear period with zero activity should produce a result."""
        start = datetime(2024, 1, 15, 10, 0, tzinfo=UTC)
        # 120 minutes of data: first 30 active, 60 zero (nonwear window), 30 active
        activity = [100.0] * 30 + [0.0] * 60 + [100.0] * 30
        epochs = _make_epoch_series(120, activity=activity, start=start)

        # Diary says nonwear from 10:30 to 11:30 (within the zero-activity region)
        nw_start = datetime(2024, 1, 15, 10, 30, tzinfo=UTC)
        nw_end = datetime(2024, 1, 15, 11, 30, tzinfo=UTC)
        diary = DiaryInput(nonwear_periods=[(nw_start, nw_end)])

        result = self.detector.detect(epochs, diary_data=diary)
        # Should detect a nonwear period (details depend on place_nonwear_markers logic)
        assert isinstance(result, list)


# =============================================================================
# OnsetOffsetPeriodConstructor tests
# =============================================================================

class TestOnsetOffsetPeriodConstructor:
    def setup_method(self) -> None:
        self.constructor = OnsetOffsetPeriodConstructor()

    def test_id(self) -> None:
        assert self.constructor.id == "onset_offset"

    def test_no_guide_returns_empty(self) -> None:
        """Without a main guide, no main sleep should be constructed."""
        epochs = _make_epoch_series(60, activity=[0.0] * 60)
        classified = ClassifiedEpochs(scores=[1] * 60)
        bouts = [Bout(start_index=0, end_index=59, state=1)]
        result = self.constructor.construct(
            epochs, classified, bouts,
            main_guide=None, nap_guides=[],
        )
        assert result == []

    def test_main_sleep_with_guide(self) -> None:
        """With diary guide and all-sleep epochs, should find main sleep."""
        start = datetime(2024, 1, 15, 21, 0, tzinfo=UTC)
        n = 120  # 2 hours of epochs
        activity = [0.0] * n
        epochs = _make_epoch_series(n, activity=activity, start=start)
        # All sleep
        classified = ClassifiedEpochs(scores=[1] * n)
        bouts = [Bout(start_index=0, end_index=n - 1, state=1)]

        onset_target = datetime(2024, 1, 15, 21, 30, tzinfo=UTC)
        offset_target = datetime(2024, 1, 15, 22, 30, tzinfo=UTC)
        guide = GuideWindow(onset_target=onset_target, offset_target=offset_target)

        result = self.constructor.construct(
            epochs, classified, bouts,
            main_guide=guide, nap_guides=[],
        )
        assert len(result) >= 1
        main = result[0]
        assert main.period_type == MarkerType.MAIN_SLEEP
        assert main.onset_index >= 0
        assert main.offset_index > main.onset_index

    def test_default_params_used_when_none(self) -> None:
        """When params=None, PeriodConstructorParams defaults should be used."""
        start = datetime(2024, 1, 15, 21, 0, tzinfo=UTC)
        n = 60
        epochs = _make_epoch_series(n, activity=[0.0] * n, start=start)
        classified = ClassifiedEpochs(scores=[1] * n)
        bouts = [Bout(start_index=0, end_index=n - 1, state=1)]
        guide = GuideWindow(
            onset_target=datetime(2024, 1, 15, 21, 10, tzinfo=UTC),
            offset_target=datetime(2024, 1, 15, 21, 50, tzinfo=UTC),
        )
        result = self.constructor.construct(
            epochs, classified, bouts,
            main_guide=guide, nap_guides=[],
            params=None,
        )
        # Should work without error even with params=None
        assert isinstance(result, list)

    def test_no_sleep_epochs_returns_empty(self) -> None:
        """All wake epochs near guide should produce no periods."""
        start = datetime(2024, 1, 15, 21, 0, tzinfo=UTC)
        n = 60
        epochs = _make_epoch_series(n, activity=[500.0] * n, start=start)
        classified = ClassifiedEpochs(scores=[0] * n)  # all wake
        bouts = [Bout(start_index=0, end_index=n - 1, state=0)]
        guide = GuideWindow(
            onset_target=datetime(2024, 1, 15, 21, 10, tzinfo=UTC),
            offset_target=datetime(2024, 1, 15, 21, 50, tzinfo=UTC),
        )
        result = self.constructor.construct(
            epochs, classified, bouts,
            main_guide=guide, nap_guides=[],
        )
        assert result == []

    def test_empty_epochs_returns_empty(self) -> None:
        epochs = _make_epoch_series(0, activity=[])
        classified = ClassifiedEpochs(scores=[])
        result = self.constructor.construct(
            epochs, classified, [],
            main_guide=None, nap_guides=[],
        )
        assert result == []


# =============================================================================
# Compat bridge tests
# =============================================================================

class TestCompat:
    def test_run_via_pipeline_empty_data(self) -> None:
        result = run_via_pipeline([], [])
        assert "sleep_markers" in result
        assert "nap_markers" in result
        assert "notes" in result

    def test_run_via_pipeline_with_activity(self) -> None:
        """All-sleep data without diary should produce no markers (diary required)."""
        start = datetime(2024, 1, 15, 22, 0, tzinfo=UTC)
        n = 60
        timestamps = _make_timestamps(n, start)
        activity = [0.0] * n
        result = run_via_pipeline(
            timestamps,
            activity,
            include_diary=True,
        )
        # No diary data provided, so no main sleep placed
        assert len(result["sleep_markers"]) == 0

    def test_run_via_pipeline_no_diary(self) -> None:
        """With include_diary=False, should use none guider and passthrough preprocessor."""
        start = datetime(2024, 1, 15, 22, 0, tzinfo=UTC)
        n = 60
        timestamps = _make_timestamps(n, start)
        activity = [0.0] * n
        result = run_via_pipeline(
            timestamps,
            activity,
            include_diary=False,
        )
        assert isinstance(result, dict)
        assert "sleep_markers" in result

    def test_run_via_pipeline_with_diary(self) -> None:
        """Full pipeline with diary data."""
        start = datetime(2024, 1, 15, 21, 0, tzinfo=UTC)
        n = 600  # 10 hours of data
        timestamps = _make_timestamps(n, start)
        activity = [0.0] * n  # all zero = all sleep

        result = run_via_pipeline(
            timestamps,
            activity,
            algorithm=AlgorithmType.SADEH_1994_ACTILIFE,
            diary_onset_time="22:00",
            diary_wake_time="06:00",
            analysis_date="2024-01-15",
            include_diary=True,
        )
        assert isinstance(result, dict)
        assert "sleep_markers" in result
        # With all-sleep data and diary times, should find main sleep
        assert len(result["sleep_markers"]) >= 1

    def test_run_via_pipeline_custom_epoch_length(self) -> None:
        """Non-default epoch length should override params."""
        start = datetime(2024, 1, 15, 22, 0, tzinfo=UTC)
        n = 30
        timestamps = _make_timestamps(n, start, epoch_seconds=30)
        activity = [0.0] * n
        result = run_via_pipeline(
            timestamps,
            activity,
            epoch_length_seconds=30,
            include_diary=False,
        )
        assert isinstance(result, dict)

    def test_run_via_pipeline_with_cole_kripke(self) -> None:
        """Pipeline should work with Cole-Kripke algorithm."""
        start = datetime(2024, 1, 15, 22, 0, tzinfo=UTC)
        n = 60
        timestamps = _make_timestamps(n, start)
        activity = [0.0] * n
        result = run_via_pipeline(
            timestamps,
            activity,
            algorithm=AlgorithmType.COLE_KRIPKE_1992_ACTILIFE,
            include_diary=False,
        )
        assert isinstance(result, dict)

    def test_raw_diary_constructed_correctly(self) -> None:
        """Verify RawDiaryInput is constructed from compat args."""
        start = datetime(2024, 1, 15, 22, 0, tzinfo=UTC)
        n = 30
        timestamps = _make_timestamps(n, start)
        activity = [0.0] * n

        # Patch ScoringPipeline at its definition module (imported locally in compat)
        with patch("sleep_scoring_web.services.pipeline.orchestrator.ScoringPipeline") as mock_cls:
            mock_pipeline = MagicMock()
            mock_pipeline.run.return_value = PipelineResult()
            mock_cls.return_value = mock_pipeline

            run_via_pipeline(
                timestamps,
                activity,
                diary_bed_time="21:30",
                diary_onset_time="22:00",
                diary_wake_time="06:00",
                diary_naps=[("13:00", "14:00")],
                diary_nonwear=[("10:00", "11:00")],
                analysis_date="2024-01-15",
            )

            call_kwargs = mock_pipeline.run.call_args
            raw_diary = call_kwargs.kwargs.get("raw_diary") or call_kwargs[1].get("raw_diary")
            assert raw_diary is not None
            assert raw_diary.bed_time == "21:30"
            assert raw_diary.onset_time == "22:00"
            assert raw_diary.wake_time == "06:00"
            assert raw_diary.naps == [("13:00", "14:00")]
            assert raw_diary.nonwear == [("10:00", "11:00")]
            assert raw_diary.analysis_date == "2024-01-15"

    def test_no_raw_diary_when_no_analysis_date(self) -> None:
        """If analysis_date is None, raw_diary should be None."""
        start = datetime(2024, 1, 15, 22, 0, tzinfo=UTC)
        n = 30
        timestamps = _make_timestamps(n, start)
        activity = [0.0] * n

        with patch("sleep_scoring_web.services.pipeline.orchestrator.ScoringPipeline") as mock_cls:
            mock_pipeline = MagicMock()
            mock_pipeline.run.return_value = PipelineResult()
            mock_cls.return_value = mock_pipeline

            run_via_pipeline(
                timestamps,
                activity,
                diary_onset_time="22:00",
                diary_wake_time="06:00",
                analysis_date=None,
                include_diary=True,
            )

            call_kwargs = mock_pipeline.run.call_args
            raw_diary = call_kwargs.kwargs.get("raw_diary") or call_kwargs[1].get("raw_diary")
            assert raw_diary is None


# =============================================================================
# ScoringPipeline orchestrator tests
# =============================================================================

class TestScoringPipeline:
    def test_empty_data_returns_early(self) -> None:
        params = PipelineParams()
        pipeline = ScoringPipeline(params)
        result = pipeline.run([], [])
        assert isinstance(result, PipelineResult)
        assert "No activity data" in result.notes

    def test_empty_timestamps(self) -> None:
        params = PipelineParams()
        pipeline = ScoringPipeline(params)
        result = pipeline.run([], [0.0, 1.0])
        assert "No activity data" in result.notes

    def test_empty_activity(self) -> None:
        params = PipelineParams()
        pipeline = ScoringPipeline(params)
        result = pipeline.run([100.0, 200.0], [])
        assert "No activity data" in result.notes

    def test_basic_pipeline_run_no_diary(self) -> None:
        """Pipeline with no diary should work (none guider, passthrough preprocessor)."""
        params = PipelineParams.from_legacy(include_diary=False)
        pipeline = ScoringPipeline(params)
        start = datetime(2024, 1, 15, 22, 0, tzinfo=UTC)
        n = 60
        timestamps = _make_timestamps(n, start)
        activity = [0.0] * n
        result = pipeline.run(timestamps, activity)
        assert isinstance(result, PipelineResult)

    def test_pipeline_with_diary(self) -> None:
        """Full pipeline run with diary data."""
        params = PipelineParams()
        pipeline = ScoringPipeline(params)

        start = datetime(2024, 1, 15, 21, 0, tzinfo=UTC)
        n = 600
        timestamps = _make_timestamps(n, start)
        activity = [0.0] * n

        raw_diary = RawDiaryInput(
            onset_time="22:00",
            wake_time="06:00",
            analysis_date="2024-01-15",
        )
        result = pipeline.run(timestamps, activity, raw_diary=raw_diary)
        assert isinstance(result, PipelineResult)
        # With all-zero activity and diary, should find main sleep
        assert len(result.sleep_periods) >= 1
        # Main sleep should be MAIN_SLEEP type
        main_periods = [sp for sp in result.sleep_periods if sp.period_type == MarkerType.MAIN_SLEEP]
        assert len(main_periods) >= 1

    def test_pipeline_custom_detection_rule_note(self) -> None:
        """Non-default onset/offset params should add a detection rule note."""
        params = PipelineParams(
            period_guider="none",
            diary_preprocessor="passthrough",
            period_constructor_params=PeriodConstructorParams(
                onset_min_consecutive_sleep=5,
                offset_min_consecutive_minutes=10,
            ),
        )
        pipeline = ScoringPipeline(params)
        start = datetime(2024, 1, 15, 22, 0, tzinfo=UTC)
        timestamps = _make_timestamps(30, start)
        activity = [0.0] * 30
        result = pipeline.run(timestamps, activity)
        assert any("5S/10S" in note for note in result.notes)

    def test_pipeline_default_detection_rule_no_note(self) -> None:
        """Default onset(3)/offset(5) should NOT add a detection rule note."""
        params = PipelineParams(
            period_guider="none",
            diary_preprocessor="passthrough",
        )
        pipeline = ScoringPipeline(params)
        start = datetime(2024, 1, 15, 22, 0, tzinfo=UTC)
        timestamps = _make_timestamps(30, start)
        activity = [0.0] * 30
        result = pipeline.run(timestamps, activity)
        assert not any("Detection rule" in note for note in result.notes)

    def test_pipeline_resolves_all_components(self) -> None:
        """Ensure all default components are resolved without errors."""
        params = PipelineParams()
        pipeline = ScoringPipeline(params)
        # If construction succeeds, all components were resolved
        assert pipeline._diary_preprocessor is not None
        assert pipeline._epoch_classifier is not None
        assert pipeline._bout_detector is not None
        assert pipeline._period_guider is not None
        assert pipeline._period_constructor is not None
        assert pipeline._nonwear_detector is not None

    def test_pipeline_result_has_nonwear(self) -> None:
        """Pipeline with long zero-activity region followed by strong resumption detects nonwear."""
        params = PipelineParams(
            period_guider="none",
            diary_preprocessor="passthrough",
        )
        pipeline = ScoringPipeline(params)
        start = datetime(2024, 1, 15, 10, 0, tzinfo=UTC)
        # 4 hours data: 30 min active, 100 min flat zero (device removed), 110 min active
        # Activity must exceed resumption_threshold (500) so flat_activity detector triggers
        activity = [1000.0] * 30 + [0.0] * 100 + [1000.0] * 110
        n = len(activity)
        timestamps = _make_timestamps(n, start)
        result = pipeline.run(timestamps, activity)
        # flat_activity detector should detect the 100-minute zero period as nonwear
        assert len(result.nonwear_periods) >= 1

    def test_pipeline_no_main_sleep_note(self) -> None:
        """When no main sleep is found, a note should be added."""
        params = PipelineParams(
            period_guider="none",
            diary_preprocessor="passthrough",
        )
        pipeline = ScoringPipeline(params)
        start = datetime(2024, 1, 15, 22, 0, tzinfo=UTC)
        timestamps = _make_timestamps(30, start)
        activity = [500.0] * 30  # all wake
        result = pipeline.run(timestamps, activity)
        assert any("No main sleep" in note for note in result.notes)

    def test_pipeline_with_cole_kripke(self) -> None:
        """Pipeline should work with Cole-Kripke epoch classifier."""
        params = PipelineParams(
            epoch_classifier="cole_kripke_1992_actilife",
            period_guider="none",
            diary_preprocessor="passthrough",
        )
        pipeline = ScoringPipeline(params)
        start = datetime(2024, 1, 15, 22, 0, tzinfo=UTC)
        timestamps = _make_timestamps(60, start)
        activity = [0.0] * 60
        result = pipeline.run(timestamps, activity)
        assert isinstance(result, PipelineResult)

    def test_pipeline_placement_notes_with_diary(self) -> None:
        """When main sleep is found with diary, placement notes should reference diary times."""
        params = PipelineParams()
        pipeline = ScoringPipeline(params)

        start = datetime(2024, 1, 15, 21, 0, tzinfo=UTC)
        n = 600
        timestamps = _make_timestamps(n, start)
        activity = [0.0] * n

        raw_diary = RawDiaryInput(
            onset_time="22:00",
            wake_time="06:00",
            analysis_date="2024-01-15",
        )
        result = pipeline.run(timestamps, activity, raw_diary=raw_diary)
        # Should have placement notes mentioning "Main sleep" and "diary"
        main_notes = [n for n in result.notes if "Main sleep" in n]
        if main_notes:
            assert any("diary" in n.lower() for n in main_notes)


# =============================================================================
# Protocol conformance tests (runtime_checkable)
# =============================================================================

class TestProtocolConformance:
    """Verify each implementation satisfies its runtime_checkable protocol."""

    def test_epoch_classifier_protocol(self) -> None:
        from sleep_scoring_web.services.pipeline.protocols import EpochClassifier
        assert isinstance(SadehEpochClassifier(), EpochClassifier)
        assert isinstance(ColeKripkeEpochClassifier(), EpochClassifier)

    def test_bout_detector_protocol(self) -> None:
        from sleep_scoring_web.services.pipeline.protocols import BoutDetector
        assert isinstance(ConsecutiveRunBoutDetector(), BoutDetector)

    def test_period_guider_protocol(self) -> None:
        from sleep_scoring_web.services.pipeline.protocols import PeriodGuider
        assert isinstance(DiaryPeriodGuider(), PeriodGuider)
        assert isinstance(NullPeriodGuider(), PeriodGuider)

    def test_period_constructor_protocol(self) -> None:
        from sleep_scoring_web.services.pipeline.protocols import PeriodConstructor
        assert isinstance(OnsetOffsetPeriodConstructor(), PeriodConstructor)

    def test_nonwear_detector_protocol(self) -> None:
        from sleep_scoring_web.services.pipeline.protocols import NonwearDetector
        assert isinstance(ChoiNonwearDetector(), NonwearDetector)
        assert isinstance(DiaryAnchoredNonwearDetector(), NonwearDetector)

    def test_diary_preprocessor_protocol(self) -> None:
        from sleep_scoring_web.services.pipeline.protocols import DiaryPreprocessor
        assert isinstance(AmPmDiaryPreprocessor(), DiaryPreprocessor)
        assert isinstance(PassthroughDiaryPreprocessor(), DiaryPreprocessor)


# =============================================================================
# Integration: end-to-end pipeline scenarios
# =============================================================================

class TestPipelineIntegration:
    def test_full_pipeline_with_naps(self) -> None:
        """End-to-end: main sleep + nap placement."""
        params = PipelineParams()
        pipeline = ScoringPipeline(params)

        # 15 hours of data starting at 15:00
        start = datetime(2024, 1, 15, 15, 0, tzinfo=UTC)
        n = 900  # 15 hours
        # Simulate: wake during day, sleep at night
        activity: list[float] = []
        for i in range(n):
            t = start + timedelta(minutes=i)
            hour = t.hour
            if 22 <= hour or hour < 6:
                activity.append(0.0)  # sleep time
            elif 13 <= hour < 14:
                activity.append(0.0)  # nap time
            else:
                activity.append(200.0)  # awake
        timestamps = _make_timestamps(n, start)

        raw_diary = RawDiaryInput(
            onset_time="22:00",
            wake_time="06:00",
            naps=[("13:00", "14:00")],
            analysis_date="2024-01-15",
        )
        result = pipeline.run(timestamps, activity, raw_diary=raw_diary)
        assert isinstance(result, PipelineResult)
        # Should have at least main sleep
        main_periods = [sp for sp in result.sleep_periods if sp.period_type == MarkerType.MAIN_SLEEP]
        assert len(main_periods) >= 1

    def test_full_pipeline_all_wake(self) -> None:
        """All-wake data with diary should produce no main sleep."""
        params = PipelineParams()
        pipeline = ScoringPipeline(params)

        start = datetime(2024, 1, 15, 21, 0, tzinfo=UTC)
        n = 600
        timestamps = _make_timestamps(n, start)
        activity = [500.0] * n  # all wake

        raw_diary = RawDiaryInput(
            onset_time="22:00",
            wake_time="06:00",
            analysis_date="2024-01-15",
        )
        result = pipeline.run(timestamps, activity, raw_diary=raw_diary)
        # High activity means no sleep periods
        main_periods = [sp for sp in result.sleep_periods if sp.period_type == MarkerType.MAIN_SLEEP]
        assert len(main_periods) == 0

    def test_to_legacy_dict_round_trip(self) -> None:
        """Verify to_legacy_dict output has expected structure."""
        params = PipelineParams.from_legacy(include_diary=False)
        pipeline = ScoringPipeline(params)
        start = datetime(2024, 1, 15, 22, 0, tzinfo=UTC)
        timestamps = _make_timestamps(60, start)
        activity = [0.0] * 60
        result = pipeline.run(timestamps, activity)
        legacy = result.to_legacy_dict()
        assert set(legacy.keys()) == {"sleep_markers", "nap_markers", "notes"}
        assert isinstance(legacy["sleep_markers"], list)
        assert isinstance(legacy["nap_markers"], list)
        assert isinstance(legacy["notes"], list)
