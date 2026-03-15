//! Cole-Kripke (1992) sleep scoring algorithm.
//!
//! Ports the Python implementation exactly:
//! - 7-epoch sliding window (4 lag + current + 2 lead)
//! - Coefficients: [106, 54, 58, 76, 230, 74, 67]
//! - Scaling factor: 0.001
//! - ActiLife variant: divide by 100, cap at 300
//! - SI < 1.0 = sleep (1), otherwise wake (0)
//! - Always uses Axis1 (Y-axis)

const COEFFICIENTS: [f64; 7] = [106.0, 54.0, 58.0, 76.0, 230.0, 74.0, 67.0];
const SCALING_FACTOR: f64 = 0.001;
const THRESHOLD: f64 = 1.0;
const ACTILIFE_SCALE: f64 = 100.0;
const ACTILIFE_CAP: f64 = 300.0;

/// Score activity data using Cole-Kripke algorithm.
///
/// # Arguments
/// * `activity` - Axis1 activity counts (1-minute epochs)
/// * `use_actilife_scaling` - If true, divide by 100 and cap at 300
///
/// # Returns
/// Vector of 1 (sleep) or 0 (wake) per epoch
pub fn score(activity: &[f64], use_actilife_scaling: bool) -> Vec<u8> {
    let n = activity.len();
    if n == 0 {
        return Vec::new();
    }

    // Single padded array: 4 zeros (lag) + scaled data + 2 zeros (lead)
    let padded_len = 4 + n + 2;
    let mut padded = vec![0.0_f64; padded_len];
    if use_actilife_scaling {
        for i in 0..n {
            padded[4 + i] = (activity[i] / ACTILIFE_SCALE).min(ACTILIFE_CAP);
        }
    } else {
        padded[4..4 + n].copy_from_slice(activity);
    }

    let mut result = vec![0u8; n];

    for i in 0..n {
        let window = &padded[i..i + 7];
        let weighted_sum: f64 = window
            .iter()
            .zip(COEFFICIENTS.iter())
            .map(|(&a, &c)| a * c)
            .sum();
        let sleep_index = SCALING_FACTOR * weighted_sum;
        result[i] = if sleep_index < THRESHOLD { 1 } else { 0 };
    }

    result
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_empty_input() {
        assert_eq!(score(&[], true), Vec::<u8>::new());
    }

    #[test]
    fn test_all_zeros_is_sleep() {
        let activity = vec![0.0; 20];
        let result = score(&activity, true);
        assert!(result.iter().all(|&v| v == 1), "All zeros = sleep");
    }

    #[test]
    fn test_high_activity_is_wake() {
        // With ActiLife scaling: 50000/100 = 500, capped to 300
        // SI = 0.001 * (106+54+58+76+230+74+67)*300 = 0.001 * 665 * 300 = 199.5 > 1.0 → wake
        let activity = vec![50000.0; 20];
        let result = score(&activity, true);
        assert!(result.iter().all(|&v| v == 0), "High activity = wake");
    }

    #[test]
    fn test_actilife_scaling() {
        // Activity of 100: scaled = 100/100 = 1.0
        // SI = 0.001 * (106+54+58+76+230+74+67)*1 = 0.001 * 665 = 0.665 < 1.0 → sleep
        let activity = vec![100.0; 20];
        let result = score(&activity, true);
        assert!(result.iter().all(|&v| v == 1), "Low activity with scaling = sleep");
    }

    #[test]
    fn test_no_scaling() {
        // Without scaling: activity of 100 used directly
        // SI = 0.001 * 665 * 100 = 66.5 > 1.0 → wake
        let activity = vec![100.0; 20];
        let result = score(&activity, false);
        assert!(result.iter().all(|&v| v == 0), "Activity 100 without scaling = wake");
    }

    #[test]
    fn test_single_epoch() {
        let result = score(&[0.0], true);
        assert_eq!(result.len(), 1);
        assert_eq!(result[0], 1, "Single zero epoch = sleep");
    }

    #[test]
    fn test_output_length_matches_input() {
        for n in [1, 5, 7, 20, 100] {
            let activity = vec![42.0; n];
            let result = score(&activity, true);
            assert_eq!(result.len(), n, "Output length must match input for n={}", n);
        }
    }

    #[test]
    fn test_output_only_binary() {
        let activity = vec![150.0; 50];
        let result = score(&activity, true);
        assert!(
            result.iter().all(|&v| v == 0 || v == 1),
            "Output must only contain 0 or 1"
        );
    }

    #[test]
    fn test_actilife_cap_at_300() {
        // With scaling: 50000/100 = 500, capped to 300
        // Same as 30000/100 = 300 (exactly at cap)
        let high = score(&vec![50000.0; 20], true);
        let at_cap = score(&vec![30000.0; 20], true);
        assert_eq!(high, at_cap, "Values above cap should produce same result");
    }

    #[test]
    fn test_boundary_at_threshold() {
        // SI = 0.001 * weighted_sum. SI < 1.0 → sleep.
        // For a single non-zero epoch surrounded by zeros:
        // SI = 0.001 * (230 * x) where x is the scaled value at position [4]
        // SI = 1.0 when x = 1000/230 ≈ 4.348
        // Without scaling, activity ~4 should be borderline sleep
        let activity = vec![4.0; 20];
        let result = score(&activity, false);
        // SI = 0.001 * sum(coeffs) * 4 = 0.001 * 665 * 4 = 2.66 > 1.0 → wake
        assert!(result.iter().all(|&v| v == 0), "Activity 4 without scaling = wake");
    }

    #[test]
    fn test_max_f64_with_scaling() {
        // Very large values should be capped, not overflow
        let activity = vec![f64::MAX; 5];
        let result = score(&activity, true);
        assert_eq!(result.len(), 5);
        // All should be wake (capped at 300, high SI)
        assert!(result.iter().all(|&v| v == 0));
    }
}
