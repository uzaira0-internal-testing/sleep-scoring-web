/// Epoching: Convert raw high-frequency accelerometer data to 60-second epoch counts.
///
/// Implements a simplified agcounts-like conversion:
/// - Sum of absolute values per axis per epoch
/// - Vector magnitude: sqrt(x^2 + y^2 + z^2)

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
) -> EpochResult {
    let samples_per_epoch = sample_freq as usize * EPOCH_SECONDS;
    let n = axis_x.len();

    if n == 0 || samples_per_epoch == 0 {
        return EpochResult {
            timestamps_ms: Vec::new(),
            axis_y: Vec::new(),
            axis_x: Vec::new(),
            axis_z: Vec::new(),
            vector_magnitude: Vec::new(),
        };
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

    EpochResult {
        timestamps_ms: epoch_timestamps,
        axis_x: epoch_x,
        axis_y: epoch_y,
        axis_z: epoch_z,
        vector_magnitude: epoch_vm,
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_empty_input() {
        let result = epoch_raw_data(&[], &[], &[], &[], 100);
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

        let result = epoch_raw_data(&timestamps, &axis_x, &axis_y, &axis_z, 100);

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

        let result = epoch_raw_data(&timestamps, &axis_x, &axis_y, &axis_z, 100);
        assert_eq!(result.timestamps_ms.len(), 1);
    }
}
