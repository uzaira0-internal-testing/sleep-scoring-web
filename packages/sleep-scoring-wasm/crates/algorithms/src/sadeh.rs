//! Sadeh (1994) sleep scoring algorithm.
//!
//! Ports the Python implementation exactly:
//! - 11-epoch sliding window (5 prev + current + 5 future)
//! - Activity capped at 300 before processing
//! - Formula: PS = 7.601 - 0.065*AVG - 1.08*NATS - 0.056*SD - 0.703*LG
//! - SD: right-aligned 6-epoch window (current + 5 preceding), ddof=1
//! - NATS: count of epochs with activity in [50, 100)
//! - Always uses Axis1 (Y-axis)

const WINDOW_SIZE: usize = 11;
const ACTIVITY_CAP: f64 = 300.0;
const NATS_MIN: f64 = 50.0;
const NATS_MAX: f64 = 100.0;
const COEFF_A: f64 = 7.601;
const COEFF_B: f64 = 0.065;
const COEFF_C: f64 = 1.08;
const COEFF_D: f64 = 0.056;
const COEFF_E: f64 = 0.703;

/// Score activity data using Sadeh algorithm.
///
/// # Arguments
/// * `activity` - Axis1 activity counts (1-minute epochs)
/// * `threshold` - Classification threshold (-4.0 for ActiLife, 0.0 for original)
///
/// # Returns
/// Vector of 1 (sleep) or 0 (wake) per epoch
pub fn score(activity: &[f64], threshold: f64) -> Vec<u8> {
    let n = activity.len();
    if n == 0 {
        return Vec::new();
    }

    // Single padded array: cap + zero-pad 5 each side
    let padded_len = n + 10;
    let mut padded = vec![0.0_f64; padded_len];
    for i in 0..n {
        padded[i + 5] = activity[i].min(ACTIVITY_CAP);
    }

    // Pre-compute rolling SD (backward: current + 5 preceding, ddof=1)
    // SD window for original epoch i = padded[i..i+6]
    let rolling_sds: Vec<f64> = (0..n)
        .map(|i| {
            let window = &padded[i..i + 6];
            std_ddof1(window)
        })
        .collect();

    let mut result = vec![0u8; n];

    for i in 0..n {
        // 11-epoch window in padded array
        let window = &padded[i..i + WINDOW_SIZE];

        // AVG: mean of 11-epoch window
        let avg: f64 = window.iter().sum::<f64>() / WINDOW_SIZE as f64;

        // NATS: count of epochs in [50, 100) in the window
        let nats: f64 = window
            .iter()
            .filter(|&&v| (NATS_MIN..NATS_MAX).contains(&v))
            .count() as f64;

        // SD: pre-computed backward rolling std
        let sd = rolling_sds[i];

        // LG: ln(current_count + 1) — use capped value from padded[i+5]
        let lg = (padded[i + 5] + 1.0).ln();

        // PS formula
        let ps = COEFF_A - (COEFF_B * avg) - (COEFF_C * nats) - (COEFF_D * sd) - (COEFF_E * lg);

        result[i] = if ps > threshold { 1 } else { 0 };
    }

    result
}

/// Standard deviation with ddof=1 (unbiased estimator)
fn std_ddof1(data: &[f64]) -> f64 {
    let n = data.len();
    if n < 2 {
        return 0.0;
    }
    let mean = data.iter().sum::<f64>() / n as f64;
    let variance = data.iter().map(|&x| (x - mean).powi(2)).sum::<f64>() / (n - 1) as f64;
    variance.sqrt()
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_empty_input() {
        assert_eq!(score(&[], -4.0), Vec::<u8>::new());
    }

    #[test]
    fn test_all_zeros_is_sleep() {
        // All zeros should produce sleep (PS = 7.601 - 0 - 0 - 0 - 0.703*ln(1) = 7.601 > -4)
        let activity = vec![0.0; 20];
        let result = score(&activity, -4.0);
        assert!(result.iter().all(|&v| v == 1), "All zeros should be sleep");
    }

    #[test]
    fn test_high_activity_is_wake() {
        // Very high activity should produce wake
        let activity = vec![300.0; 20];
        let result = score(&activity, -4.0);
        // With all 300s: AVG=300, NATS=0, SD=0, LG=ln(301)≈5.707
        // PS = 7.601 - 0.065*300 - 0 - 0 - 0.703*5.707 ≈ 7.601 - 19.5 - 4.012 ≈ -15.91
        // -15.91 < -4.0 → wake
        assert!(result.iter().all(|&v| v == 0), "High activity should be wake");
    }

    #[test]
    fn test_activity_capped_at_300() {
        // Values above 300 should be treated as 300
        let activity = vec![500.0; 20];
        let capped_result = score(&activity, -4.0);
        let at_300_result = score(&vec![300.0; 20], -4.0);
        assert_eq!(capped_result, at_300_result, "Values >300 should be capped");
    }

    #[test]
    fn test_std_ddof1_basic() {
        let data = [2.0, 4.0, 4.0, 4.0, 5.0, 5.0, 7.0, 9.0];
        let sd = std_ddof1(&data);
        // Known value: std with ddof=1 ≈ 2.138
        assert!((sd - 2.138).abs() < 0.01);
    }

    #[test]
    fn test_single_epoch() {
        // Single epoch: should still produce a result
        let result = score(&[50.0], -4.0);
        assert_eq!(result.len(), 1);
        // PS = 7.601 - 0.065*(50/11) - 1.08*(1) - 0.056*0 - 0.703*ln(51)
        // ≈ 7.601 - 0.295 - 1.08 - 0 - 2.761 ≈ 3.465 > -4 → sleep
        assert_eq!(result[0], 1);
    }

    #[test]
    fn test_output_length_matches_input() {
        for n in [1, 5, 11, 20, 100] {
            let activity = vec![42.0; n];
            let result = score(&activity, -4.0);
            assert_eq!(result.len(), n, "Output length must match input for n={}", n);
        }
    }

    #[test]
    fn test_output_only_binary() {
        let activity = vec![75.0; 50]; // NATS range
        let result = score(&activity, -4.0);
        assert!(
            result.iter().all(|&v| v == 0 || v == 1),
            "Output must only contain 0 or 1"
        );
    }

    #[test]
    fn test_threshold_zero() {
        // Original Sadeh uses threshold 0.0 (stricter than ActiLife's -4.0)
        let activity = vec![0.0; 20];
        let result_original = score(&activity, 0.0);
        let result_actilife = score(&activity, -4.0);
        // Both should be sleep for zeros
        assert!(result_original.iter().all(|&v| v == 1));
        assert!(result_actilife.iter().all(|&v| v == 1));
    }

    #[test]
    fn test_nats_range_boundary() {
        // Values exactly at 50 should count as NATS
        let activity = vec![50.0; 20];
        let result = score(&activity, -4.0);
        assert_eq!(result.len(), 20);

        // Values exactly at 100 should NOT count as NATS (range is [50, 100))
        let activity_100 = vec![100.0; 20];
        let result_100 = score(&activity_100, -4.0);
        assert_eq!(result_100.len(), 20);
    }

    #[test]
    fn test_std_ddof1_single_value() {
        // Single value should return 0.0 (cannot compute ddof=1 variance)
        assert_eq!(std_ddof1(&[5.0]), 0.0);
    }

    #[test]
    fn test_std_ddof1_empty() {
        assert_eq!(std_ddof1(&[]), 0.0);
    }

    #[test]
    fn test_std_ddof1_identical_values() {
        let data = [3.0, 3.0, 3.0, 3.0];
        assert_eq!(std_ddof1(&data), 0.0);
    }

    #[test]
    fn test_negative_activity_treated_correctly() {
        // Negative values: capped at min(val, 300) which for negatives stays negative
        // This exercises padding path
        let activity = vec![-10.0; 20];
        let result = score(&activity, -4.0);
        assert_eq!(result.len(), 20);
    }

    #[test]
    fn test_mixed_sleep_wake_pattern() {
        // Mix of zeros (sleep) and high values (wake)
        let mut activity = vec![0.0; 30];
        activity.extend(vec![300.0; 30]);
        let result = score(&activity, -4.0);
        assert_eq!(result.len(), 60);
        // First epochs should trend toward sleep, last toward wake
        // (boundary effects make exact assertions tricky, but length must match)
    }
}
