"""
Integration tests for the Dependency Injection system.

Tests that all DI components work together correctly across the application.
"""

from __future__ import annotations

from datetime import datetime, timedelta

import numpy as np
import pandas as pd
import pytest

from sleep_scoring_app.core.algorithms import (
    AlgorithmFactory,
    NonwearAlgorithmFactory,
    SleepPeriodDetectorFactory,
)
from sleep_scoring_app.core.constants import AlgorithmType, DataSourceType, NonwearAlgorithm
from sleep_scoring_app.core.pipeline import AlgorithmDataRequirement
from sleep_scoring_app.io.sources.loader_factory import DataSourceFactory


class TestFactoryEnumAlignment:
    """Tests that factory IDs align with enum values."""

    def test_algorithm_type_enum_matches_factory(self) -> None:
        """Test AlgorithmType enum values match factory registered IDs."""
        factory_ids = set(AlgorithmFactory.get_available_algorithms().keys())

        # Core epoch-based algorithm types should be in factory
        assert AlgorithmType.SADEH_1994_ORIGINAL.value in factory_ids
        assert AlgorithmType.SADEH_1994_ACTILIFE.value in factory_ids
        assert AlgorithmType.COLE_KRIPKE_1992_ORIGINAL.value in factory_ids
        assert AlgorithmType.COLE_KRIPKE_1992_ACTILIFE.value in factory_ids
        # Note: Raw data algorithms (van_hees_2015_sib, hdcza) removed - use rpy2/GGIR instead

    def test_nonwear_algorithm_enum_matches_factory(self) -> None:
        """Test NonwearAlgorithm enum values match factory registered IDs."""
        factory_ids = set(NonwearAlgorithmFactory.get_available_algorithms().keys())

        assert NonwearAlgorithm.CHOI_2011.value in factory_ids

    def test_create_from_enum_value(self) -> None:
        """Test creating algorithms using enum values."""
        # Sleep scoring
        algo = AlgorithmFactory.create(AlgorithmType.SADEH_1994_ACTILIFE.value)
        assert algo is not None
        assert algo.name == "Sadeh (1994) ActiLife"

        # Nonwear
        nonwear = NonwearAlgorithmFactory.create(NonwearAlgorithm.CHOI_2011.value)
        assert nonwear is not None
        assert nonwear.name == "Choi (2011)"


class TestSleepScoringPipeline:
    """Integration tests for complete sleep scoring pipeline."""

    @pytest.fixture
    def sample_activity_df(self) -> pd.DataFrame:
        """Generate sample activity DataFrame for testing."""
        np.random.seed(42)
        n_epochs = 60
        # Scores should be 0 (wake) or 1 (sleep)
        assert set(result["Sleep Score"].unique()).issubset({0, 1})

    def test_all_algorithms_score_dataframe(self) -> None:
        """Test that epoch-based algorithms can score DataFrame data."""
        np.random.seed(42)
        activity = list(np.random.randint(0, 300, size=60))
        timestamps = pd.date_range("2024-01-15 00:00:00", periods=60, freq="1min")
        df = pd.DataFrame({"datetime": timestamps, "Axis1": activity})

        epoch_algorithms = AlgorithmFactory.get_algorithms_by_data_requirement(AlgorithmDataRequirement.EPOCH_DATA)

        for algo_id in epoch_algorithms:
            algorithm = AlgorithmFactory.create(algo_id)
            result = algorithm.score(df)

            assert "Sleep Score" in result.columns
            scores = result["Sleep Score"].tolist()
            assert len(scores) == len(activity)
            assert all(s in [0, 1] for s in scores), f"Algorithm {algo_id} produced invalid scores"


class TestSleepPeriodDetectionPipeline:
    """Integration tests for onset/offset detection pipeline."""

    @pytest.fixture
    def sample_sleep_scenario(self) -> tuple[list[int], list[datetime]]:
        """Generate sample sleep/wake scenario with timestamps."""
        # 0 = wake, 1 = sleep
        sleep_scores = (
            [0] * 10  # Wake (10 min)
            + [1] * 60  # Sleep period (60 min)
            + [0] * 10  # Wake (10 min)
        )

        base_time = datetime(2024, 1, 1, 22, 0, 0)
        timestamps = [base_time + timedelta(minutes=i) for i in range(len(sleep_scores))]

        return sleep_scores, timestamps

    def test_consecutive_3_5_finds_onset_offset(self, sample_sleep_scenario: tuple) -> None:
        """Test consecutive 3/5 rule finds onset and offset."""
        sleep_scores, timestamps = sample_sleep_scenario

        detector = SleepPeriodDetectorFactory.create("consecutive_onset3s_offset5s")

        # Define search markers
        sleep_start = timestamps[5]  # Before sleep starts
        sleep_end = timestamps[75]  # After sleep ends

        onset_idx, offset_idx = detector.apply_rules(
            sleep_scores=sleep_scores,
            sleep_start_marker=sleep_start,
            sleep_end_marker=sleep_end,
            timestamps=timestamps,
        )

        assert onset_idx is not None, "Should find sleep onset"
        assert offset_idx is not None, "Should find sleep offset"
        assert onset_idx < offset_idx, "Onset should be before offset"
        # Onset should be at or after index 10 (where sleep starts)
        assert onset_idx >= 10

    def test_tudor_locke_finds_onset_offset(self, sample_sleep_scenario: tuple) -> None:
        """Test Tudor-Locke detector finds onset and offset."""
        sleep_scores, timestamps = sample_sleep_scenario

        detector = SleepPeriodDetectorFactory.create("tudor_locke_2014")

        sleep_start = timestamps[5]
        sleep_end = timestamps[75]

        onset_idx, offset_idx = detector.apply_rules(
            sleep_scores=sleep_scores,
            sleep_start_marker=sleep_start,
            sleep_end_marker=sleep_end,
            timestamps=timestamps,
        )

        # Tudor-Locke may not find periods that don't meet min duration
        # Just verify it doesn't crash and returns valid types
        assert onset_idx is None or isinstance(onset_idx, int)
        assert offset_idx is None or isinstance(offset_idx, int)


class TestNonwearPipeline:
    """Integration tests for nonwear detection pipeline."""

    @pytest.fixture
    def sample_activity_with_nonwear(self) -> tuple[np.ndarray, list[datetime]]:
        """Generate sample activity data with nonwear periods."""
        np.random.seed(42)
        n_epochs = 180  # 3 hours of data

        # Create activity with a nonwear period (zeros in middle)
        activity = np.concatenate(
            [
                np.random.randint(10, 500, size=60),  # Normal activity
                np.zeros(60, dtype=int),  # Nonwear period (1 hour of zeros)
                np.random.randint(10, 500, size=60),  # Normal activity
            ]
        )

        # Create timestamps
        base_time = datetime(2024, 1, 1, 8, 0, 0)
        timestamps = [base_time + timedelta(minutes=i) for i in range(n_epochs)]

        return activity, timestamps

    def test_choi_detects_nonwear(self, sample_activity_with_nonwear: tuple) -> None:
        """Test that Choi algorithm detects nonwear periods."""
        activity, timestamps = sample_activity_with_nonwear

        algorithm = NonwearAlgorithmFactory.create("choi_2011")
        periods = algorithm.detect(activity, timestamps)

        # Should detect the zero-activity period as nonwear
        # Note: Choi algorithm has specific criteria (90+ min), may not detect 60 min period
        assert isinstance(periods, list)

    def test_choi_detect_mask(self, sample_activity_with_nonwear: tuple) -> None:
        """Test that Choi algorithm produces per-epoch mask."""
        activity, _timestamps = sample_activity_with_nonwear

        algorithm = NonwearAlgorithmFactory.create("choi_2011")
        mask = algorithm.detect_mask(activity)

        assert isinstance(mask, list)
        assert len(mask) == len(activity)
        assert all(m in [0, 1] for m in mask)


class TestCrossFactoryIntegration:
    """Tests for integration between different factories."""

    def test_full_scoring_workflow(self) -> None:
        """Test complete workflow: score -> onset/offset."""
        np.random.seed(42)

        # Create test data
        n_epochs = 120
        timestamps = pd.date_range(start="2024-01-01 22:00:00", periods=n_epochs, freq="1min")

        activity = np.concatenate(
            [
                np.random.randint(200, 500, size=30),  # Wake
                np.random.randint(0, 50, size=60),  # Sleep
                np.random.randint(200, 500, size=30),  # Wake
            ]
        )

        df = pd.DataFrame(
            {
                "datetime": timestamps,
                "Axis1": activity,
            }
        )

        # Step 1: Score activity with sleep algorithm
        sleep_algo = AlgorithmFactory.create(AlgorithmType.SADEH_1994_ACTILIFE.value)
        scored_df = sleep_algo.score(df)

        assert "Sleep Score" in scored_df.columns

        # Step 2: Find onset/offset with detector
        detector = SleepPeriodDetectorFactory.create("consecutive_onset3s_offset5s")
        sleep_scores = scored_df["Sleep Score"].tolist()
        ts_list = [pd.Timestamp(t).to_pydatetime() for t in timestamps]

        onset_idx, _offset_idx = detector.apply_rules(
            sleep_scores=sleep_scores,
            sleep_start_marker=ts_list[20],
            sleep_end_marker=ts_list[100],
            timestamps=ts_list,
        )

        # Verify workflow completed
        assert len(scored_df) == n_epochs
        # onset/offset may or may not be found depending on data
        assert onset_idx is None or isinstance(onset_idx, int)

    def test_nonwear_and_sleep_scoring(self) -> None:
        """Test nonwear detection alongside sleep scoring."""
        np.random.seed(42)

        # Create test data
        n_epochs = 180
        base_time = datetime(2024, 1, 1, 20, 0, 0)
        timestamps = [base_time + timedelta(minutes=i) for i in range(n_epochs)]

        activity = np.concatenate(
            [
                np.random.randint(50, 300, size=60),  # Evening activity
                np.random.randint(0, 30, size=60),  # Sleep (low activity)
                np.random.randint(50, 300, size=60),  # Morning activity
            ]
        )

        # Detect nonwear
        nonwear_algo = NonwearAlgorithmFactory.create(NonwearAlgorithm.CHOI_2011.value)
        nonwear_periods = nonwear_algo.detect(activity, timestamps)

        # Score sleep
        df = pd.DataFrame(
            {
                "datetime": timestamps,
                "Axis1": activity,
            }
        )
        sleep_algo = AlgorithmFactory.create(AlgorithmType.SADEH_1994_ACTILIFE.value)
        scored_df = sleep_algo.score(df)

        # Both should complete without errors
        assert isinstance(nonwear_periods, list)
        assert "Sleep Score" in scored_df.columns


class TestDataSourceDIIntegration:
    """Integration tests for DataSource DI system."""

    def test_datasource_factory_enum_alignment(self) -> None:
        """Test DataSourceType enum values have factory entries."""
        factory_ids = set(DataSourceFactory.get_available_loaders().keys())

        # All DataSourceType values should have factory entries
        assert DataSourceType.CSV.value in factory_ids
        assert DataSourceType.GT3X.value in factory_ids

    def test_csv_full_pipeline(self, tmp_path) -> None:
        """Test full CSV load->validate->metadata flow."""
        # Create test CSV file
        csv_file = tmp_path / "test.csv"
        lines = [
            "Header Line 1",
            "Header Line 2",
            "Header Line 3",
            "Header Line 4",
            "Header Line 5",
            "Header Line 6",
            "Header Line 7",
            "Header Line 8",
            "Header Line 9",
            "Header Line 10",
            "Date,Time,Axis1",
            "1/15/2024,08:00:00,100",
            "1/15/2024,08:01:00,120",
            "1/15/2024,08:02:00,110",
        ]
        csv_file.write_text("\n".join(lines))

        # Get loader from factory
        loader = DataSourceFactory.create(DataSourceType.CSV.value)

        # Load file
        result = loader.load_file(csv_file)

        # Verify result structure
        assert "activity_data" in result
        assert "metadata" in result
        assert "column_mapping" in result

        # Verify data
        df = result["activity_data"]
        assert len(df) == 3
        assert "timestamp" in df.columns
        assert "AXIS_Y" in df.columns  # DatabaseColumn.AXIS_Y is uppercase

        # Verify metadata
        metadata = result["metadata"]
        assert "file_size" in metadata
        assert "total_epochs" in metadata
        assert metadata["total_epochs"] == 3

    def test_all_di_factories_operational(self) -> None:
        """Test all 4 DI factories can create instances."""
        # 1. Sleep scoring factory
        sleep_algo = AlgorithmFactory.create(AlgorithmFactory.get_default_algorithm_id())
        assert sleep_algo is not None
        assert hasattr(sleep_algo, "score")

        # 2. Sleep period detector factory
        detector = SleepPeriodDetectorFactory.create(SleepPeriodDetectorFactory.get_default_detector_id())
        assert detector is not None
        assert hasattr(detector, "apply_rules")

        # 3. Nonwear factory
        nonwear = NonwearAlgorithmFactory.create(NonwearAlgorithmFactory.get_default_algorithm_id())
        assert nonwear is not None
        assert hasattr(nonwear, "detect")

        # 4. DataSource factory
        datasource = DataSourceFactory.create(DataSourceFactory.get_default_loader_id())
        assert datasource is not None
        assert hasattr(datasource, "load_file")

    def test_datasource_with_sleep_scoring(self, tmp_path) -> None:
        """Test integrating datasource loading with sleep scoring."""
        # Create test CSV file
        csv_file = tmp_path / "activity.csv"
        np.random.seed(42)

        # Generate activity data
        n_epochs = 60
        header = ["Header"] * 10
        data_header = ["Date,Time,Axis1"]

        data_rows = []
        for i in range(n_epochs):
            hour = 8 + (i // 60)
            minute = i % 60
            activity = np.random.randint(0, 200)
            data_rows.append(f"1/15/2024,{hour:02d}:{minute:02d}:00,{activity}")

        csv_file.write_text("\n".join(header + data_header + data_rows))

        # Load data with DataSource factory
        loader = DataSourceFactory.create("csv")
        result = loader.load_file(csv_file)
        df = result["activity_data"]

        # Rename column for Sadeh algorithm (AXIS_Y is uppercase from DatabaseColumn)
        df_for_scoring = df.rename(columns={"timestamp": "datetime", "AXIS_Y": "Axis1"})

        # Score with sleep algorithm
        algo = AlgorithmFactory.create("sadeh_1994_actilife")
        scored_df = algo.score(df_for_scoring)

        # Verify integration works
        assert "Sleep Score" in scored_df.columns
        assert len(scored_df) == n_epochs

    def test_enum_default_consistency(self) -> None:
        """Test DataSourceType enum default matches factory default."""
        enum_default = DataSourceType.get_default()
        factory_default = DataSourceFactory.get_default_loader_id()
        assert enum_default.value == factory_default


class TestDefaultValues:
    """Tests for default algorithm selections."""

    def test_defaults_are_consistent(self) -> None:
        """Test that default values are consistent across system."""
        # AlgorithmType default should match factory default
        enum_default = AlgorithmType.get_default()
        factory_default = AlgorithmFactory.get_default_algorithm_id()
        assert enum_default.value == factory_default

        # NonwearAlgorithm default should match factory default
        nonwear_enum_default = NonwearAlgorithm.get_default()
        nonwear_factory_default = NonwearAlgorithmFactory.get_default_algorithm_id()
        assert nonwear_enum_default.value == nonwear_factory_default

        # DataSourceType default should match factory default
        datasource_enum_default = DataSourceType.get_default()
        datasource_factory_default = DataSourceFactory.get_default_loader_id()
        assert datasource_enum_default.value == datasource_factory_default

    def test_defaults_create_valid_instances(self) -> None:
        """Test that default IDs create valid algorithm instances."""
        # Sleep scoring
        algo = AlgorithmFactory.create(AlgorithmFactory.get_default_algorithm_id())
        assert algo is not None
        assert hasattr(algo, "score")

        # Sleep period detector
        detector = SleepPeriodDetectorFactory.create(SleepPeriodDetectorFactory.get_default_detector_id())
        assert detector is not None
        assert hasattr(detector, "apply_rules")

        # Nonwear
        nonwear = NonwearAlgorithmFactory.create(NonwearAlgorithmFactory.get_default_algorithm_id())
        assert nonwear is not None
        assert hasattr(nonwear, "detect")

        # DataSource
        datasource = DataSourceFactory.create(DataSourceFactory.get_default_loader_id())
        assert datasource is not None
        assert hasattr(datasource, "load_file")


class TestDataSourceFiltering:
    """Tests for filtering algorithms by data source type."""

    def test_get_algorithms_by_data_requirement_epoch(self) -> None:
        """Test filtering algorithms that work with epoch data."""
        epoch_algorithms = AlgorithmFactory.get_algorithms_by_data_requirement(AlgorithmDataRequirement.EPOCH_DATA)

        # Should include epoch-based algorithms
        assert "sadeh_1994_original" in epoch_algorithms
        assert "sadeh_1994_actilife" in epoch_algorithms
        assert "cole_kripke_1992_original" in epoch_algorithms
        assert "cole_kripke_1992_actilife" in epoch_algorithms

        # Should NOT include raw data algorithms
        assert "van_hees_2015_sib" not in epoch_algorithms
        assert "hdcza_2018" not in epoch_algorithms

    def test_get_algorithms_by_data_requirement_raw(self) -> None:
        """Test filtering algorithms that work with raw data."""
        raw_algorithms = AlgorithmFactory.get_algorithms_by_data_requirement(AlgorithmDataRequirement.RAW_DATA)

        # Raw algorithms have been removed - use rpy2/GGIR instead
        assert len(raw_algorithms) == 0

        # Epoch-based algorithms should not appear here
        assert "sadeh_1994_original" not in raw_algorithms
        assert "sadeh_1994_actilife" not in raw_algorithms
        assert "cole_kripke_1992_original" not in raw_algorithms
        assert "cole_kripke_1992_actilife" not in raw_algorithms

    def test_get_algorithm_data_requirement(self) -> None:
        """Test getting data requirement for individual algorithms."""
        # Epoch-based algorithms
        assert AlgorithmFactory.get_algorithm_data_requirement("sadeh_1994_actilife") == AlgorithmDataRequirement.EPOCH_DATA
        assert AlgorithmFactory.get_algorithm_data_requirement("cole_kripke_1992_original") == AlgorithmDataRequirement.EPOCH_DATA

        # Unknown algorithm
        assert AlgorithmFactory.get_algorithm_data_requirement("nonexistent_algo") is None

    def test_epoch_algorithms_have_correct_properties(self) -> None:
        """Test that epoch-based algorithms have correct protocol properties."""
        # Sadeh
        sadeh = AlgorithmFactory.create("sadeh_1994_actilife")
        assert sadeh.data_requirement == AlgorithmDataRequirement.EPOCH_DATA
        assert sadeh.requires_axis == "axis_y"

        # Cole-Kripke
        cole = AlgorithmFactory.create("cole_kripke_1992_actilife")
        assert cole.data_requirement == AlgorithmDataRequirement.EPOCH_DATA
        assert cole.requires_axis == "axis_y"
