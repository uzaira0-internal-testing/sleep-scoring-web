"""
Tests for PipelineOrchestrator in core/pipeline/orchestrator.py.

Tests pipeline routing based on data source and algorithm compatibility.
"""

from __future__ import annotations

from unittest.mock import MagicMock

import pandas as pd
import pytest

from sleep_scoring_app.core.pipeline.exceptions import IncompatiblePipelineError
from sleep_scoring_app.core.pipeline.orchestrator import (
    PipelineOrchestrator,
    PipelineResult,
)
from sleep_scoring_app.core.pipeline.types import (
    AlgorithmDataRequirement,
    DataSourceType,
    PipelineType,
)


@pytest.fixture
def mock_epoching_service() -> MagicMock:
    """Create a mock epoching service."""
    service = MagicMock()
    service.create_epochs.return_value = pd.DataFrame({"datetime": ["2024-01-15 08:00:00"], "Axis1": [100], "Sleep Score": [0]})
    return service


@pytest.fixture
def orchestrator(mock_epoching_service: MagicMock) -> PipelineOrchestrator:
    """Create a PipelineOrchestrator with mock epoching service."""
    return PipelineOrchestrator(mock_epoching_service)


@pytest.fixture
def orchestrator_no_epoching() -> PipelineOrchestrator:
    """Create a PipelineOrchestrator without epoching service."""
    return PipelineOrchestrator(None)


@pytest.fixture
def mock_epoch_algorithm() -> MagicMock:
    """Create a mock epoch-based algorithm (like Sadeh)."""
    algorithm = MagicMock()
    algorithm.name = "Sadeh (1994)"
    algorithm.data_requirement = AlgorithmDataRequirement.EPOCH_DATA
    algorithm.score.return_value = pd.DataFrame({"datetime": ["2024-01-15 08:00:00"], "Axis1": [100], "Sleep Score": [1]})
    return algorithm


@pytest.fixture
def mock_raw_algorithm() -> MagicMock:
    """Create a mock raw-data algorithm (like Van Hees SIB)."""
    algorithm = MagicMock()
    algorithm.name = "van Hees SIB (2015)"
    algorithm.data_requirement = AlgorithmDataRequirement.RAW_DATA
    algorithm.score.return_value = pd.DataFrame({"datetime": ["2024-01-15 08:00:00"], "AXIS_X": [0.5], "Sleep Score": [0]})
    return algorithm


@pytest.fixture
def sample_raw_data() -> pd.DataFrame:
    """Sample raw tri-axial DataFrame."""
    return pd.DataFrame(
        {
            "timestamp": ["2024-01-15 08:00:00"],
            "AXIS_X": [0.5],
            "AXIS_Y": [0.2],
            "AXIS_Z": [-0.8],
        }
    )


@pytest.fixture
def sample_epoch_data() -> pd.DataFrame:
    """Sample epoch count DataFrame."""
    return pd.DataFrame({"datetime": ["2024-01-15 08:00:00"], "Axis1": [100]})


class TestPipelineOrchestratorInit:
    """Tests for PipelineOrchestrator initialization."""

    def test_creates_with_epoching_service(self, mock_epoching_service: MagicMock) -> None:
        """Creates orchestrator with epoching service."""
        orchestrator = PipelineOrchestrator(mock_epoching_service)

        assert orchestrator._epoching_service is mock_epoching_service

    def test_creates_without_epoching_service(self) -> None:
        """Creates orchestrator without epoching service."""
        orchestrator = PipelineOrchestrator(None)

        assert orchestrator._epoching_service is None


class TestDeterminePipelineType:
    """Tests for determine_pipeline_type method."""

    def test_raw_source_raw_algo_returns_raw_to_raw(self, orchestrator: PipelineOrchestrator, mock_raw_algorithm: MagicMock) -> None:
        """Raw source + raw algorithm = RAW_TO_RAW."""
        result = orchestrator.determine_pipeline_type(DataSourceType.GT3X_RAW, mock_raw_algorithm)

        assert result == PipelineType.RAW_TO_RAW

    def test_csv_raw_source_raw_algo_returns_raw_to_raw(self, orchestrator: PipelineOrchestrator, mock_raw_algorithm: MagicMock) -> None:
        """CSV_RAW source + raw algorithm = RAW_TO_RAW."""
        result = orchestrator.determine_pipeline_type(DataSourceType.CSV_RAW, mock_raw_algorithm)

        assert result == PipelineType.RAW_TO_RAW

    def test_raw_source_epoch_algo_returns_raw_to_epoch(self, orchestrator: PipelineOrchestrator, mock_epoch_algorithm: MagicMock) -> None:
        """Raw source + epoch algorithm = RAW_TO_EPOCH."""
        result = orchestrator.determine_pipeline_type(DataSourceType.GT3X_RAW, mock_epoch_algorithm)

        assert result == PipelineType.RAW_TO_EPOCH

    def test_csv_raw_source_epoch_algo_returns_raw_to_epoch(self, orchestrator: PipelineOrchestrator, mock_epoch_algorithm: MagicMock) -> None:
        """CSV_RAW source + epoch algorithm = RAW_TO_EPOCH."""
        result = orchestrator.determine_pipeline_type(DataSourceType.CSV_RAW, mock_epoch_algorithm)

        assert result == PipelineType.RAW_TO_EPOCH

    def test_epoch_source_epoch_algo_returns_epoch_direct(self, orchestrator: PipelineOrchestrator, mock_epoch_algorithm: MagicMock) -> None:
        """Epoch source + epoch algorithm = EPOCH_DIRECT."""
        result = orchestrator.determine_pipeline_type(DataSourceType.CSV_EPOCH, mock_epoch_algorithm)

        assert result == PipelineType.EPOCH_DIRECT

    def test_epoch_source_raw_algo_returns_incompatible(self, orchestrator: PipelineOrchestrator, mock_raw_algorithm: MagicMock) -> None:
        """Epoch source + raw algorithm = INCOMPATIBLE."""
        result = orchestrator.determine_pipeline_type(DataSourceType.CSV_EPOCH, mock_raw_algorithm)

        assert result == PipelineType.INCOMPATIBLE


class TestIsCompatible:
    """Tests for is_compatible method."""

    def test_returns_true_for_compatible(self, orchestrator: PipelineOrchestrator, mock_epoch_algorithm: MagicMock) -> None:
        """Returns True for compatible combinations."""
        result = orchestrator.is_compatible(DataSourceType.CSV_EPOCH, mock_epoch_algorithm)

        assert result is True

    def test_returns_false_for_incompatible(self, orchestrator: PipelineOrchestrator, mock_raw_algorithm: MagicMock) -> None:
        """Returns False for incompatible combinations."""
        result = orchestrator.is_compatible(DataSourceType.CSV_EPOCH, mock_raw_algorithm)

        assert result is False


class TestValidateCompatibility:
    """Tests for validate_compatibility method."""

    def test_does_not_raise_for_compatible(self, orchestrator: PipelineOrchestrator, mock_epoch_algorithm: MagicMock) -> None:
        """Does not raise for compatible combinations."""
        # Should not raise
        orchestrator.validate_compatibility(DataSourceType.CSV_EPOCH, mock_epoch_algorithm)

    def test_raises_for_incompatible(self, orchestrator: PipelineOrchestrator, mock_raw_algorithm: MagicMock) -> None:
        """Raises IncompatiblePipelineError for incompatible combinations."""
        with pytest.raises(IncompatiblePipelineError) as exc_info:
            orchestrator.validate_compatibility(DataSourceType.CSV_EPOCH, mock_raw_algorithm)

        assert exc_info.value.data_source == DataSourceType.CSV_EPOCH
        assert exc_info.value.algorithm_name == "van Hees SIB (2015)"


class TestProcess:
    """Tests for process method."""

    def test_process_epoch_direct(
        self,
        orchestrator: PipelineOrchestrator,
        mock_epoch_algorithm: MagicMock,
        sample_epoch_data: pd.DataFrame,
    ) -> None:
        """Processes epoch data directly."""
        result = orchestrator.process(DataSourceType.CSV_EPOCH, sample_epoch_data, mock_epoch_algorithm)

        assert isinstance(result, PipelineResult)
        assert result.pipeline_type == PipelineType.EPOCH_DIRECT
        assert result.algorithm_name == "Sadeh (1994)"
        mock_epoch_algorithm.score.assert_called_once()

    def test_process_raw_to_raw(
        self,
        orchestrator: PipelineOrchestrator,
        mock_raw_algorithm: MagicMock,
        sample_raw_data: pd.DataFrame,
    ) -> None:
        """Processes raw data with raw algorithm."""
        result = orchestrator.process(DataSourceType.GT3X_RAW, sample_raw_data, mock_raw_algorithm)

        assert result.pipeline_type == PipelineType.RAW_TO_RAW
        mock_raw_algorithm.score.assert_called_once()

    def test_process_raw_to_epoch(
        self,
        orchestrator: PipelineOrchestrator,
        mock_epoch_algorithm: MagicMock,
        mock_epoching_service: MagicMock,
        sample_raw_data: pd.DataFrame,
    ) -> None:
        """Processes raw data through epoching then epoch algorithm."""
        result = orchestrator.process(DataSourceType.GT3X_RAW, sample_raw_data, mock_epoch_algorithm)

        assert result.pipeline_type == PipelineType.RAW_TO_EPOCH
        mock_epoching_service.create_epochs.assert_called_once()
        mock_epoch_algorithm.score.assert_called_once()

    def test_process_raises_for_incompatible(
        self,
        orchestrator: PipelineOrchestrator,
        mock_raw_algorithm: MagicMock,
        sample_epoch_data: pd.DataFrame,
    ) -> None:
        """Raises error for incompatible combinations."""
        with pytest.raises(IncompatiblePipelineError):
            orchestrator.process(DataSourceType.CSV_EPOCH, sample_epoch_data, mock_raw_algorithm)

    def test_result_contains_metadata(
        self,
        orchestrator: PipelineOrchestrator,
        mock_epoch_algorithm: MagicMock,
        sample_epoch_data: pd.DataFrame,
    ) -> None:
        """Result contains processing metadata."""
        result = orchestrator.process(DataSourceType.CSV_EPOCH, sample_epoch_data, mock_epoch_algorithm)

        assert result.metadata is not None
        assert "num_epochs" in result.metadata
        assert "sleep_epochs" in result.metadata
        assert "sleep_percentage" in result.metadata


class TestRawToEpochWithoutService:
    """Tests for RAW_TO_EPOCH pipeline without epoching service."""

    def test_raises_runtime_error(
        self,
        orchestrator_no_epoching: PipelineOrchestrator,
        mock_epoch_algorithm: MagicMock,
        sample_raw_data: pd.DataFrame,
    ) -> None:
        """Raises RuntimeError when epoching service not provided."""
        with pytest.raises(RuntimeError) as exc_info:
            orchestrator_no_epoching.process(DataSourceType.GT3X_RAW, sample_raw_data, mock_epoch_algorithm)

        assert "epoching service" in str(exc_info.value).lower()


class TestFindScoreColumn:
    """Tests for _find_score_column method."""

    def test_finds_sleep_score(self, orchestrator: PipelineOrchestrator) -> None:
        """Finds 'Sleep Score' column."""
        df = pd.DataFrame({"datetime": ["2024-01-15"], "Sleep Score": [1]})

        result = orchestrator._find_score_column(df)

        assert result == "Sleep Score"

    def test_finds_score_case_insensitive(self, orchestrator: PipelineOrchestrator) -> None:
        """Finds score column case-insensitively."""
        df = pd.DataFrame({"datetime": ["2024-01-15"], "my_score_column": [1]})

        result = orchestrator._find_score_column(df)

        assert result == "my_score_column"

    def test_raises_for_no_score_column(self, orchestrator: PipelineOrchestrator) -> None:
        """Raises ValueError when no score column found."""
        df = pd.DataFrame({"datetime": ["2024-01-15"], "data": [100]})

        with pytest.raises(ValueError) as exc_info:
            orchestrator._find_score_column(df)

        assert "No score column found" in str(exc_info.value)


class TestPipelineResult:
    """Tests for PipelineResult dataclass."""

    def test_creates_result(self) -> None:
        """Creates PipelineResult with all fields."""
        df = pd.DataFrame({"Sleep Score": [0, 1, 0]})
        result = PipelineResult(
            scored_data=df,
            pipeline_type=PipelineType.EPOCH_DIRECT,
            data_source=DataSourceType.CSV_EPOCH,
            algorithm_name="Sadeh (1994)",
            metadata={"num_epochs": 3},
        )

        assert len(result.scored_data) == 3
        assert result.pipeline_type == PipelineType.EPOCH_DIRECT
        assert result.data_source == DataSourceType.CSV_EPOCH
        assert result.algorithm_name == "Sadeh (1994)"
        assert result.metadata["num_epochs"] == 3

    def test_metadata_optional(self) -> None:
        """Metadata is optional."""
        df = pd.DataFrame({"Sleep Score": [0]})
        result = PipelineResult(
            scored_data=df,
            pipeline_type=PipelineType.EPOCH_DIRECT,
            data_source=DataSourceType.CSV_EPOCH,
            algorithm_name="Sadeh (1994)",
        )

        assert result.metadata is None


class TestPipelineType:
    """Tests for PipelineType enum methods."""

    def test_raw_to_raw_is_valid(self) -> None:
        """RAW_TO_RAW is a valid pipeline."""
        assert PipelineType.RAW_TO_RAW.is_valid() is True

    def test_raw_to_epoch_is_valid(self) -> None:
        """RAW_TO_EPOCH is a valid pipeline."""
        assert PipelineType.RAW_TO_EPOCH.is_valid() is True

    def test_epoch_direct_is_valid(self) -> None:
        """EPOCH_DIRECT is a valid pipeline."""
        assert PipelineType.EPOCH_DIRECT.is_valid() is True

    def test_incompatible_is_not_valid(self) -> None:
        """INCOMPATIBLE is not a valid pipeline."""
        assert PipelineType.INCOMPATIBLE.is_valid() is False

    def test_raw_to_epoch_requires_epoching(self) -> None:
        """RAW_TO_EPOCH requires epoching."""
        assert PipelineType.RAW_TO_EPOCH.requires_epoching() is True

    def test_raw_to_raw_does_not_require_epoching(self) -> None:
        """RAW_TO_RAW does not require epoching."""
        assert PipelineType.RAW_TO_RAW.requires_epoching() is False

    def test_epoch_direct_does_not_require_epoching(self) -> None:
        """EPOCH_DIRECT does not require epoching."""
        assert PipelineType.EPOCH_DIRECT.requires_epoching() is False

    def test_raw_to_raw_is_raw_pipeline(self) -> None:
        """RAW_TO_RAW is a raw pipeline."""
        assert PipelineType.RAW_TO_RAW.is_raw_pipeline() is True

    def test_raw_to_epoch_is_raw_pipeline(self) -> None:
        """RAW_TO_EPOCH is a raw pipeline."""
        assert PipelineType.RAW_TO_EPOCH.is_raw_pipeline() is True

    def test_epoch_direct_is_epoch_pipeline(self) -> None:
        """EPOCH_DIRECT is an epoch pipeline."""
        assert PipelineType.EPOCH_DIRECT.is_epoch_pipeline() is True


class TestIncompatiblePipelineError:
    """Tests for IncompatiblePipelineError exception."""

    def test_creates_with_details(self) -> None:
        """Creates error with all details."""
        error = IncompatiblePipelineError(
            data_source=DataSourceType.CSV_EPOCH,
            algorithm_requirement=AlgorithmDataRequirement.RAW_DATA,
            algorithm_name="van Hees SIB (2015)",
        )

        assert error.data_source == DataSourceType.CSV_EPOCH
        assert error.algorithm_requirement == AlgorithmDataRequirement.RAW_DATA
        assert error.algorithm_name == "van Hees SIB (2015)"
        assert error.reason is not None
        assert error.suggestion is not None

    def test_generates_reason(self) -> None:
        """Generates meaningful reason."""
        error = IncompatiblePipelineError(
            data_source=DataSourceType.CSV_EPOCH,
            algorithm_requirement=AlgorithmDataRequirement.RAW_DATA,
            algorithm_name="van Hees SIB (2015)",
        )

        assert "raw" in error.reason.lower()
        assert "epoch" in error.reason.lower()

    def test_generates_suggestion(self) -> None:
        """Generates helpful suggestion."""
        error = IncompatiblePipelineError(
            data_source=DataSourceType.CSV_EPOCH,
            algorithm_requirement=AlgorithmDataRequirement.RAW_DATA,
            algorithm_name="van Hees SIB (2015)",
        )

        assert "GT3X" in error.suggestion or "raw" in error.suggestion.lower()
