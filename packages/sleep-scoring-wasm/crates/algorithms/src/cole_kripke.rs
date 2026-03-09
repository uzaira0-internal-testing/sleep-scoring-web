/// Cole-Kripke (1992) sleep scoring algorithm.
///
/// Ports the Python implementation exactly:
/// - 7-epoch sliding window (4 lag + current + 2 lead)
/// - Coefficients: [106, 54, 58, 76, 230, 74, 67]
/// - Scaling factor: 0.001
/// - ActiLife variant: divide by 100, cap at 300
/// - SI < 1.0 = sleep (1), otherwise wake (0)
/// - Always uses Axis1 (Y-axis)

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

    // Apply scaling
    let scaled: Vec<f64> = if use_actilife_scaling {
        activity
            .iter()
            .map(|&v| (v / ACTILIFE_SCALE).min(ACTILIFE_CAP))
            .collect()
    } else {
        activity.to_vec()
    };

    // Pad: 4 zeros at start (for lag), 2 zeros at end (for lead)
    let mut padded = vec![0.0_f64; 4];
    padded.extend_from_slice(&scaled);
    padded.extend(vec![0.0_f64; 2]);

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
}
