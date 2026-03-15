//! Epoching: Convert raw high-frequency accelerometer data to 60-second epoch counts.
//!
//! Implements a simplified agcounts-like conversion:
//! - Sum of absolute values per axis per epoch
//! - Vector magnitude: sqrt(x^2 + y^2 + z^2)

use crate::types::EpochResult;

const EPOCH_SECONDS: usize = 60;

/// Convert raw tri-axial data to 60-second epoch counts.
///
/// # Arguments
/// * `timestamps_ms` - Timestamps in milliseconds
/// * `axis_x` - X-axis raw values (g)
/// * `axis_y` - Y-axis raw values (g)
/// * `axis_z` - Z-axis raw values (g)
/// * `sample_freq` - Sample frequency in Hz
///
/// # Returns
/// EpochResult with epoch-level activity counts
pub fn epoch_raw_data(
    timestamps_ms: &[f64],
    axis_x: &[f64],
    axis_y: &[f64],
    axis_z: &[f64],
    sample_freq: u32,
) -> Result<EpochResult, String> {
    let samples_per_epoch = sample_freq as usize * EPOCH_SECONDS;
    let n = axis_x.len();

    // Validate all input arrays have the same length to prevent out-of-bounds panics
    if timestamps_ms.len() != n {
        return Err(format!(
            "timestamps_ms length ({}) must match axis_x length ({})",
            timestamps_ms.len(),
            n
        ));
    }
    if axis_y.len() != n {
        return Err(format!(
            "axis_y length ({}) must match axis_x length ({})",
            axis_y.len(),
            n
        ));
    }
    if axis_z.len() != n {
        return Err(format!(
            "axis_z length ({}) must match axis_x length ({})",
            axis_z.len(),
            n
        ));
    }

    if n == 0 || samples_per_epoch == 0 {
        return Ok(EpochResult {
            timestamps_ms: Vec::new(),
            axis_y: Vec::new(),
            axis_x: Vec::new(),
            axis_z: Vec::new(),
            vector_magnitude: Vec::new(),
        });
    }

    let n_epochs = n / samples_per_epoch;
    let mut epoch_timestamps = Vec::with_capacity(n_epochs);
    let mut epoch_x = Vec::with_capacity(n_epochs);
    let mut epoch_y = Vec::with_capacity(n_epochs);
    let mut epoch_z = Vec::with_capacity(n_epochs);
    let mut epoch_vm = Vec::with_capacity(n_epochs);

    for epoch_idx in 0..n_epochs {
        let start = epoch_idx * samples_per_epoch;
        let end = start + samples_per_epoch;

        // Epoch timestamp = first sample timestamp
        epoch_timestamps.push(timestamps_ms[start]);

        // Single-pass: accumulate all three axes simultaneously
        let mut sum_x = 0.0_f64;
        let mut sum_y = 0.0_f64;
        let mut sum_z = 0.0_f64;
        for j in start..end {
            sum_x += axis_x[j].abs();
            sum_y += axis_y[j].abs();
            sum_z += axis_z[j].abs();
        }

        epoch_x.push(sum_x);
        epoch_y.push(sum_y);
        epoch_z.push(sum_z);
        epoch_vm.push((sum_x * sum_x + sum_y * sum_y + sum_z * sum_z).sqrt());
    }

    Ok(EpochResult {
        timestamps_ms: epoch_timestamps,
        axis_x: epoch_x,
        axis_y: epoch_y,
        axis_z: epoch_z,
        vector_magnitude: epoch_vm,
    })
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_empty_input() {
        let result = epoch_raw_data(&[], &[], &[], &[], 100).unwrap();
        assert!(result.timestamps_ms.is_empty());
    }

    #[test]
    fn test_single_epoch() {
        let samples_per_epoch = 100 * 60; // 6000 samples
        let n = samples_per_epoch;

        let timestamps: Vec<f64> = (0..n).map(|i| i as f64 * 10.0).collect(); // 10ms intervals
        let axis_x = vec![1.0; n];
        let axis_y = vec![2.0; n];
        let axis_z = vec![0.5; n];

        let result = epoch_raw_data(&timestamps, &axis_x, &axis_y, &axis_z, 100).unwrap();

        assert_eq!(result.timestamps_ms.len(), 1);
        assert_eq!(result.axis_x[0], 6000.0); // sum of abs(1.0) * 6000
        assert_eq!(result.axis_y[0], 12000.0); // sum of abs(2.0) * 6000
        assert_eq!(result.axis_z[0], 3000.0); // sum of abs(0.5) * 6000
    }

    #[test]
    fn test_partial_epoch_dropped() {
        // 1.5 epochs worth of data → only 1 epoch output
        let samples_per_epoch = 100 * 60;
        let n = samples_per_epoch + samples_per_epoch / 2;

        let timestamps: Vec<f64> = (0..n).map(|i| i as f64 * 10.0).collect();
        let axis_x = vec![1.0; n];
        let axis_y = vec![1.0; n];
        let axis_z = vec![1.0; n];

        let result = epoch_raw_data(&timestamps, &axis_x, &axis_y, &axis_z, 100).unwrap();
        assert_eq!(result.timestamps_ms.len(), 1);
    }

    #[test]
    fn test_mismatched_lengths_returns_error() {
        let result = epoch_raw_data(&[1.0, 2.0], &[1.0], &[1.0], &[1.0], 100);
        assert!(result.is_err());
        assert!(result.unwrap_err().contains("timestamps_ms length"));
    }

    #[test]
    fn test_mismatched_axis_y_returns_error() {
        let result = epoch_raw_data(&[1.0], &[1.0], &[1.0, 2.0], &[1.0], 100);
        assert!(result.is_err());
        assert!(result.unwrap_err().contains("axis_y length"));
    }

    #[test]
    fn test_mismatched_axis_z_returns_error() {
        let result = epoch_raw_data(&[1.0], &[1.0], &[1.0], &[1.0, 2.0], 100);
        assert!(result.is_err());
        assert!(result.unwrap_err().contains("axis_z length"));
    }

    #[test]
    fn test_multiple_epochs() {
        let samples_per_epoch = 100 * 60; // 6000 samples
        let n = samples_per_epoch * 3; // 3 full epochs

        let timestamps: Vec<f64> = (0..n).map(|i| i as f64 * 10.0).collect();
        let axis_x = vec![1.0; n];
        let axis_y = vec![1.0; n];
        let axis_z = vec![1.0; n];

        let result = epoch_raw_data(&timestamps, &axis_x, &axis_y, &axis_z, 100).unwrap();

        assert_eq!(result.timestamps_ms.len(), 3);
        assert_eq!(result.axis_x.len(), 3);
        // Each epoch: sum of abs(1.0) * 6000 = 6000
        assert_eq!(result.axis_x[0], 6000.0);
        assert_eq!(result.axis_x[1], 6000.0);
        assert_eq!(result.axis_x[2], 6000.0);
        // Timestamps should be first sample of each epoch
        assert_eq!(result.timestamps_ms[0], 0.0);
        assert_eq!(result.timestamps_ms[1], 60000.0);
        assert_eq!(result.timestamps_ms[2], 120000.0);
    }

    #[test]
    fn test_vector_magnitude_calculation() {
        let samples_per_epoch = 100 * 60;
        let n = samples_per_epoch;

        let timestamps: Vec<f64> = (0..n).map(|i| i as f64 * 10.0).collect();
        let axis_x = vec![3.0; n];
        let axis_y = vec![4.0; n];
        let axis_z = vec![0.0; n];

        let result = epoch_raw_data(&timestamps, &axis_x, &axis_y, &axis_z, 100).unwrap();

        // sum_x = 3*6000 = 18000, sum_y = 4*6000 = 24000, sum_z = 0
        // VM = sqrt(18000^2 + 24000^2) = sqrt(324M + 576M) = sqrt(900M) = 30000
        assert!((result.vector_magnitude[0] - 30000.0).abs() < 0.01);
    }

    #[test]
    fn test_negative_values_use_abs() {
        let samples_per_epoch = 100 * 60;
        let n = samples_per_epoch;

        let timestamps: Vec<f64> = (0..n).map(|i| i as f64 * 10.0).collect();
        let axis_x = vec![-1.0; n];
        let axis_y = vec![-2.0; n];
        let axis_z = vec![-0.5; n];

        let result = epoch_raw_data(&timestamps, &axis_x, &axis_y, &axis_z, 100).unwrap();

        // abs(-1.0) * 6000 = 6000
        assert_eq!(result.axis_x[0], 6000.0);
        assert_eq!(result.axis_y[0], 12000.0);
        assert_eq!(result.axis_z[0], 3000.0);
    }

    #[test]
    fn test_different_sample_rates() {
        // 50 Hz: 50 * 60 = 3000 samples per epoch
        let samples_per_epoch = 50 * 60;
        let n = samples_per_epoch;

        let timestamps: Vec<f64> = (0..n).map(|i| i as f64 * 20.0).collect();
        let axis_x = vec![1.0; n];
        let axis_y = vec![1.0; n];
        let axis_z = vec![1.0; n];

        let result = epoch_raw_data(&timestamps, &axis_x, &axis_y, &axis_z, 50).unwrap();

        assert_eq!(result.timestamps_ms.len(), 1);
        assert_eq!(result.axis_x[0], 3000.0);
    }

    #[test]
    fn test_fewer_samples_than_one_epoch() {
        // Less than one epoch worth of data → 0 epochs
        let timestamps = vec![0.0; 100];
        let axis_x = vec![1.0; 100];
        let axis_y = vec![1.0; 100];
        let axis_z = vec![1.0; 100];

        let result = epoch_raw_data(&timestamps, &axis_x, &axis_y, &axis_z, 100).unwrap();
        assert!(result.timestamps_ms.is_empty());
    }
}
