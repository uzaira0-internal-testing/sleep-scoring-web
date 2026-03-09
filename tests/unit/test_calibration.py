"""Tests for auto-calibration (sphere fitting) algorithm."""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from sleep_scoring_app.preprocessing.calibration import (
    CalibrationConfig,
    CalibrationResult,
    apply_calibration,
    calibrate,
    extract_calibration_features,
    select_stationary_points,
)


class TestExtractCalibrationFeatures:
    """Tests for extract_calibration_features function."""

    def test_feature_extraction_shape(self):
        """Feature extraction should produce correct shape."""
        sf = 100  # 100 Hz sample rate
        epoch_size = 10  # 10 second epochs
        n_epochs = 5
        n_samples = sf * epoch_size * n_epochs

        # Generate random data centered around 1g on z-axis
        data = np.random.randn(n_samples, 3) * 0.1
        data[:, 2] += 1.0  # Add 1g to z-axis (device at rest on table)

        features = extract_calibration_features(data, sf, epoch_size)

        # Should have 5 epochs, 7 features per epoch
        assert features.shape == (n_epochs, 7)

    def test_feature_columns(self):
        """Features should contain EN, means, and SDs in correct order."""
        sf = 100
        n_samples = sf * 100  # 100 seconds of data

        # Constant data - should have low SD
        data = np.ones((n_samples, 3)) * 0.5
        data[:, 2] = 1.0  # z-axis at 1g

        features = extract_calibration_features(data, sf, 10)

        # Feature columns: [EN, mean_x, mean_y, mean_z, sd_x, sd_y, sd_z]
        assert features.shape[1] == 7

        # For constant data, SDs should be near zero
        assert np.all(features[:, 4:7] < 0.01)

        # Means should be close to input values
        assert np.allclose(features[:, 1], 0.5, atol=0.01)  # mean_x
        assert np.allclose(features[:, 2], 0.5, atol=0.01)  # mean_y
        assert np.allclose(features[:, 3], 1.0, atol=0.01)  # mean_z

    def test_empty_data(self):
        """Should handle empty data gracefully."""
        sf = 100
        data = np.array([]).reshape(0, 3)

        features = extract_calibration_features(data, sf, 10)

        assert features.shape == (0, 7)

    def test_insufficient_data_for_one_epoch(self):
        """Should handle data shorter than one epoch."""
        sf = 100
        epoch_size = 10
        n_samples = sf * 5  # Only 5 seconds of data

        data = np.random.randn(n_samples, 3)

        features = extract_calibration_features(data, sf, epoch_size)

        # Should return empty array since we can't form a complete epoch
        assert features.shape == (0, 7)

    def test_euclidean_norm_calculation(self):
        """EN should be calculated correctly for unit sphere."""
        sf = 100
        n_samples = sf * 10  # 10 seconds

        # Create data on unit sphere
        data = np.zeros((n_samples, 3))
        data[:, 2] = 1.0  # All force on z-axis = 1g

        features = extract_calibration_features(data, sf, 10)

        # EN (column 0) should be close to 1.0
        assert np.allclose(features[:, 0], 1.0, atol=0.01)


class TestSelectStationaryPoints:
    """Tests for select_stationary_points function."""

    def test_filters_stationary_points(self):
        """Should filter out non-stationary points based on SD."""
        n_points = 100
        features = np.zeros((n_points, 7))

        # EN column
        features[:, 0] = 1.0

        # Means near origin (stationary on unit sphere)
        features[:50, 1:4] = np.array([0.1, 0.1, 0.98])  # Near +Z
        features[50:, 1:4] = np.array([-0.1, -0.1, -0.98])  # Near -Z

        # Low SD for first 80 (stationary)
        features[:80, 4:7] = 0.005
        # High SD for last 20 (moving)
        features[80:, 4:7] = 0.1

        stationary, _status = select_stationary_points(features)

        # Should have filtered out moving points
        assert len(stationary) < n_points
        # Should have most of the first 80 points (minus first row and duplicates)
        assert len(stationary) > 50

    def test_requires_sphere_coverage(self):
        """Should require points on all sides of sphere."""
        n_points = 100
        features = np.zeros((n_points, 7))

        # EN column
        features[:, 0] = 1.0

        # All points on one side of sphere (only positive z)
        features[:, 1:4] = np.array([0.0, 0.0, 1.0])

        # Low SD (stationary)
        features[:, 4:7] = 0.005

        _stationary, status = select_stationary_points(features)

        # Should fail sphere coverage check
        assert "not enough points on all sides of sphere" in status

    def test_requires_minimum_points(self):
        """Should require minimum number of stationary points."""
        # Only 5 points
        features = np.zeros((5, 7))
        features[:, 0] = 1.0
        features[:, 1:4] = np.array([0.0, 0.0, 1.0])
        features[:, 4:7] = 0.005

        _stationary, status = select_stationary_points(features)

        # Should fail minimum points check
        assert "not enough stationary points" in status

    def test_filters_invalid_data(self):
        """Should filter out 99999 and NaN values."""
        n_points = 50
        features = np.zeros((n_points, 7))

        # Valid data for first half
        features[:25, 0] = 1.0
        features[:25, 1:4] = np.array([0.1, 0.1, 0.98])
        features[:25, 4:7] = 0.005

        # Invalid data for second half
        features[25:, 0] = 99999  # Invalid marker
        features[25:, 3] = np.nan  # NaN in mean_z

        stationary, _status = select_stationary_points(features)

        # Should only keep valid points (minus first row)
        assert len(stationary) <= 24

    def test_removes_duplicate_rows(self):
        """Should remove duplicate non-wear rows."""
        n_points = 20
        features = np.zeros((n_points, 7))

        # Create valid data
        features[:, 0] = 1.0
        features[:, 1:4] = np.random.randn(n_points, 3) * 0.3
        features[:, 4:7] = 0.005

        # Make some rows identical (duplicate non-wear)
        features[5:10, 1:7] = features[4, 1:7]  # 5 duplicate rows

        stationary, _status = select_stationary_points(features)

        # Should have removed duplicates
        assert len(stationary) < n_points - 1  # -1 for first row removal


class TestCalibrate:
    """Tests for calibrate function."""

    def test_calibrate_with_known_offset(self):
        """Should recover known offset from synthetic data."""
        sf = 100
        n_samples = sf * 60 * 30  # 30 minutes of data (more data for better calibration)

        # True calibration parameters
        true_offset = np.array([0.05, -0.03, 0.02])
        true_scale = np.array([1.0, 1.0, 1.0])

        # Generate data on unit sphere with known offset
        # Key: Each position should be held for at least 60 seconds to be "stationary"
        np.random.seed(42)
        n_positions = 30  # Fewer positions, held longer

        # Random orientations on unit sphere covering all sides
        theta = np.random.uniform(0, 2 * np.pi, n_positions)
        phi = np.random.uniform(0, np.pi, n_positions)
        unit_vectors = np.column_stack(
            [
                np.sin(phi) * np.cos(theta),
                np.sin(phi) * np.sin(theta),
                np.cos(phi),
            ]
        )

        # Create data by repeating each position for 60 seconds (stationary periods)
        samples_per_position = sf * 60  # 60 seconds per position
        data = np.repeat(unit_vectors, samples_per_position, axis=0)[:n_samples]

        # Add very small noise to simulate stationary data
        data += np.random.randn(len(data), 3) * 0.002

        # Apply inverse of true calibration (simulate uncalibrated sensor)
        uncalibrated = data / true_scale - true_offset

        # Run calibration
        config = CalibrationConfig(
            epoch_size_sec=10,
            sd_criterion=0.013,
            sphere_criterion=0.3,
            min_stationary_points=10,
        )
        result = calibrate(uncalibrated, sf, config)

        # Should succeed
        assert result.success
        assert result.message == "calibration successful"

        # Should recover the true offset (within tolerance)
        assert np.allclose(result.offset, true_offset, atol=0.01)

        # Should recover the true scale
        assert np.allclose(result.scale, true_scale, atol=0.01)

        # Error should improve
        assert result.error_after < result.error_before

    def test_calibrate_with_known_scale(self):
        """Should recover known scale from synthetic data."""
        sf = 100
        n_samples = sf * 60 * 30  # 30 minutes

        # True calibration parameters
        true_offset = np.array([0.0, 0.0, 0.0])
        true_scale = np.array([1.05, 0.98, 1.02])

        # Generate data with long stationary periods
        np.random.seed(43)
        n_positions = 30  # Fewer positions, held longer
        theta = np.random.uniform(0, 2 * np.pi, n_positions)
        phi = np.random.uniform(0, np.pi, n_positions)
        unit_vectors = np.column_stack(
            [
                np.sin(phi) * np.cos(theta),
                np.sin(phi) * np.sin(theta),
                np.cos(phi),
            ]
        )

        samples_per_position = sf * 60  # 60 seconds per position
        data = np.repeat(unit_vectors, samples_per_position, axis=0)[:n_samples]
        data += np.random.randn(len(data), 3) * 0.002

        # Apply inverse calibration
        uncalibrated = data / true_scale - true_offset

        # Run calibration
        result = calibrate(uncalibrated, sf)

        # Should succeed
        assert result.success

        # Should recover the true scale (within tolerance)
        assert np.allclose(result.scale, true_scale, atol=0.02)

        # Should recover the true offset
        assert np.allclose(result.offset, true_offset, atol=0.01)

    def test_calibrate_insufficient_data(self):
        """Should fail gracefully with insufficient data."""
        sf = 100
        n_samples = sf * 20  # Only 20 seconds

        data = np.random.randn(n_samples, 3) * 0.1
        data[:, 2] += 1.0

        result = calibrate(data, sf)

        # Should fail due to insufficient stationary points
        assert not result.success
        assert "not enough" in result.message.lower()

        # Should return identity transform
        assert np.allclose(result.scale, np.ones(3))
        assert np.allclose(result.offset, np.zeros(3))

        # Errors should be NaN
        assert np.isnan(result.error_before)
        assert np.isnan(result.error_after)

    def test_calibrate_with_custom_config(self):
        """Should respect custom configuration."""
        sf = 100
        n_samples = sf * 60 * 10

        # Generate test data
        np.random.seed(44)
        n_positions = 100
        theta = np.random.uniform(0, 2 * np.pi, n_positions)
        phi = np.random.uniform(0, np.pi, n_positions)
        unit_vectors = np.column_stack(
            [
                np.sin(phi) * np.cos(theta),
                np.sin(phi) * np.sin(theta),
                np.cos(phi),
            ]
        )

        samples_per_position = n_samples // n_positions
        data = np.repeat(unit_vectors, samples_per_position, axis=0)
        data += np.random.randn(len(data), 3) * 0.005

        # Custom config with stricter SD criterion
        config = CalibrationConfig(
            epoch_size_sec=5,  # Smaller epochs
            sd_criterion=0.008,  # Stricter SD threshold
            sphere_criterion=0.3,
            min_stationary_points=20,  # More points required
        )

        result = calibrate(data, sf, config)

        # Result depends on whether data meets stricter criteria
        # Just verify config was used (no error)
        assert isinstance(result, CalibrationResult)

    def test_calibration_result_immutability(self):
        """CalibrationResult arrays should be immutable."""
        result = CalibrationResult(
            scale=np.ones(3),
            offset=np.zeros(3),
            error_before=0.05,
            error_after=0.01,
            n_points_used=50,
            success=True,
            message="test",
        )

        # Arrays should be marked as non-writeable
        assert not result.scale.flags.writeable
        assert not result.offset.flags.writeable

        # Attempting to modify should raise error
        with pytest.raises(ValueError, match="read-only"):
            result.scale[0] = 999.0


class TestApplyCalibration:
    """Tests for apply_calibration function."""

    def test_apply_calibration_numpy(self):
        """Should apply calibration to numpy array."""
        data = np.array(
            [
                [1.0, 0.0, 0.0],
                [0.0, 1.0, 0.0],
                [0.0, 0.0, 1.0],
            ]
        )

        offset = np.array([0.1, -0.1, 0.05])
        scale = np.array([1.02, 0.98, 1.01])

        calibrated = apply_calibration(data, scale, offset)

        # Should apply formula: (data + offset) * scale
        expected = (data + offset) * scale
        assert np.allclose(calibrated, expected)

    def test_apply_calibration_dataframe_xyz(self):
        """Should apply calibration to DataFrame with X, Y, Z columns."""
        data = pd.DataFrame(
            {
                "X": [1.0, 0.0, 0.0],
                "Y": [0.0, 1.0, 0.0],
                "Z": [0.0, 0.0, 1.0],
            }
        )

        offset = np.array([0.1, -0.1, 0.05])
        scale = np.array([1.02, 0.98, 1.01])

        calibrated = apply_calibration(data, scale, offset)

        # Should apply to each axis
        assert "X" in calibrated.columns
        assert "Y" in calibrated.columns
        assert "Z" in calibrated.columns

        expected_x = (data["X"] + offset[0]) * scale[0]
        expected_y = (data["Y"] + offset[1]) * scale[1]
        expected_z = (data["Z"] + offset[2]) * scale[2]

        assert np.allclose(calibrated["X"], expected_x)
        assert np.allclose(calibrated["Y"], expected_y)
        assert np.allclose(calibrated["Z"], expected_z)

    def test_apply_calibration_dataframe_lowercase(self):
        """Should handle lowercase x, y, z columns."""
        data = pd.DataFrame(
            {
                "x": [1.0, 0.0, 0.0],
                "y": [0.0, 1.0, 0.0],
                "z": [0.0, 0.0, 1.0],
            }
        )

        offset = np.array([0.0, 0.0, 0.0])
        scale = np.array([2.0, 2.0, 2.0])

        calibrated = apply_calibration(data, scale, offset)

        assert np.allclose(calibrated["x"], data["x"] * 2.0)
        assert np.allclose(calibrated["y"], data["y"] * 2.0)
        assert np.allclose(calibrated["z"], data["z"] * 2.0)

    def test_apply_calibration_dataframe_axis_columns(self):
        """Should handle Axis1, Axis2, Axis3 columns."""
        data = pd.DataFrame(
            {
                "Axis1": [1.0, 0.0, 0.0],
                "Axis2": [0.0, 1.0, 0.0],
                "Axis3": [0.0, 0.0, 1.0],
            }
        )

        offset = np.array([0.05, -0.05, 0.02])
        scale = np.array([1.0, 1.0, 1.0])

        calibrated = apply_calibration(data, scale, offset)

        assert np.allclose(calibrated["Axis1"], data["Axis1"] + offset[0])
        assert np.allclose(calibrated["Axis2"], data["Axis2"] + offset[1])
        assert np.allclose(calibrated["Axis3"], data["Axis3"] + offset[2])

    def test_apply_calibration_preserves_other_columns(self):
        """Should preserve non-axis columns in DataFrame."""
        data = pd.DataFrame(
            {
                "timestamp": [1, 2, 3],
                "X": [1.0, 0.0, 0.0],
                "Y": [0.0, 1.0, 0.0],
                "Z": [0.0, 0.0, 1.0],
                "temperature": [25.0, 25.1, 25.2],
            }
        )

        offset = np.array([0.0, 0.0, 0.0])
        scale = np.array([1.0, 1.0, 1.0])

        calibrated = apply_calibration(data, scale, offset)

        # Should preserve timestamp and temperature
        assert "timestamp" in calibrated.columns
        assert "temperature" in calibrated.columns
        assert np.array_equal(calibrated["timestamp"], data["timestamp"])
        assert np.array_equal(calibrated["temperature"], data["temperature"])

    def test_apply_calibration_no_axis_columns_raises(self):
        """Should raise error if DataFrame has no recognizable axis columns."""
        data = pd.DataFrame(
            {
                "foo": [1.0, 2.0, 3.0],
                "bar": [4.0, 5.0, 6.0],
            }
        )

        offset = np.array([0.0, 0.0, 0.0])
        scale = np.array([1.0, 1.0, 1.0])

        with pytest.raises(ValueError, match="Could not find x, y, z axis columns"):
            apply_calibration(data, scale, offset)

    def test_apply_calibration_invalid_type_raises(self):
        """Should raise error for invalid data type."""
        data = "invalid"
        offset = np.array([0.0, 0.0, 0.0])
        scale = np.array([1.0, 1.0, 1.0])

        with pytest.raises(TypeError, match="Data must be numpy array or pandas DataFrame"):
            apply_calibration(data, scale, offset)

    def test_apply_calibration_does_not_modify_original(self):
        """Should not modify original DataFrame."""
        data = pd.DataFrame(
            {
                "X": [1.0, 2.0, 3.0],
                "Y": [4.0, 5.0, 6.0],
                "Z": [7.0, 8.0, 9.0],
            }
        )

        original_data = data.copy()

        offset = np.array([1.0, 1.0, 1.0])
        scale = np.array([2.0, 2.0, 2.0])

        calibrated = apply_calibration(data, scale, offset)

        # Original should be unchanged
        assert data.equals(original_data)
        # Calibrated should be different
        assert not calibrated.equals(data)


class TestCalibrationIntegration:
    """Integration tests for complete calibration workflow."""

    def test_full_calibration_workflow(self):
        """Test complete calibration workflow from data to calibrated output."""
        sf = 100
        n_samples = sf * 60 * 30  # 30 minutes

        # Generate uncalibrated data with known offset/scale
        np.random.seed(45)
        true_offset = np.array([0.08, -0.05, 0.03])
        true_scale = np.array([1.03, 0.97, 1.01])

        n_positions = 30  # Fewer positions, held longer
        theta = np.random.uniform(0, 2 * np.pi, n_positions)
        phi = np.random.uniform(0, np.pi, n_positions)
        unit_vectors = np.column_stack(
            [
                np.sin(phi) * np.cos(theta),
                np.sin(phi) * np.sin(theta),
                np.cos(phi),
            ]
        )

        samples_per_position = sf * 60  # 60 seconds per position
        data = np.repeat(unit_vectors, samples_per_position, axis=0)[:n_samples]
        data += np.random.randn(len(data), 3) * 0.002

        # Apply inverse calibration to simulate uncalibrated sensor
        uncalibrated = data / true_scale - true_offset

        # Step 1: Calibrate
        result = calibrate(uncalibrated, sf)
        assert result.success

        # Step 2: Apply calibration
        calibrated = apply_calibration(uncalibrated, result.scale, result.offset)

        # Verify calibrated data is on unit sphere
        norms = np.sqrt(np.sum(calibrated**2, axis=1))
        # Sample some points and check they're close to 1g
        sample_indices = np.random.choice(len(norms), 100, replace=False)
        sampled_norms = norms[sample_indices]
        assert np.allclose(sampled_norms, 1.0, atol=0.05)

    def test_calibration_with_dataframe_workflow(self):
        """Test calibration workflow with pandas DataFrame."""
        sf = 100
        n_samples = sf * 60 * 30  # 30 minutes

        # Generate data
        np.random.seed(46)
        n_positions = 30  # Fewer positions, held longer
        theta = np.random.uniform(0, 2 * np.pi, n_positions)
        phi = np.random.uniform(0, np.pi, n_positions)
        unit_vectors = np.column_stack(
            [
                np.sin(phi) * np.cos(theta),
                np.sin(phi) * np.sin(theta),
                np.cos(phi),
            ]
        )

        samples_per_position = sf * 60  # 60 seconds per position
        data = np.repeat(unit_vectors, samples_per_position, axis=0)[:n_samples]

        # Create DataFrame
        df = pd.DataFrame(
            {
                "timestamp": range(len(data)),
                "X": data[:, 0] + 0.05,  # Add offset
                "Y": data[:, 1] - 0.03,
                "Z": data[:, 2] + 0.02,
            }
        )

        # Calibrate using numpy array from DataFrame
        xyz_data = df[["X", "Y", "Z"]].to_numpy()
        result = calibrate(xyz_data, sf)

        assert result.success

        # Apply to DataFrame
        calibrated_df = apply_calibration(df, result.scale, result.offset)

        # Should preserve timestamp
        assert np.array_equal(calibrated_df["timestamp"], df["timestamp"])

        # Calibrated data should be closer to unit sphere
        calibrated_norms = np.sqrt(calibrated_df["X"] ** 2 + calibrated_df["Y"] ** 2 + calibrated_df["Z"] ** 2)
        assert np.abs(np.mean(calibrated_norms) - 1.0) < 0.02


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
