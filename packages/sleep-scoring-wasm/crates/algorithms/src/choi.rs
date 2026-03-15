//! Choi (2011) nonwear detection algorithm.
//!
//! Ports the Python implementation exactly:
//! - Finds consecutive zero-count periods
//! - Allows spikes of up to spike_tolerance (2) non-zero minutes within a window
//! - Minimum period length: 90 minutes
//! - Window size for spike checking: 30 minutes
//! - Merges adjacent periods within 1 minute

const MIN_PERIOD_LENGTH: usize = 90;
const SPIKE_TOLERANCE: usize = 2;
const WINDOW_SIZE: usize = 30;

struct NonwearPeriod {
    start_idx: usize,
    end_idx: usize,
}

/// Detect nonwear periods using Choi algorithm.
///
/// # Arguments
/// * `counts` - Activity counts (1-minute epochs, typically vector magnitude)
///
/// # Returns
/// Vector of 1 (nonwear) or 0 (wear) per epoch
pub fn detect(counts: &[f64]) -> Vec<u8> {
    let n = counts.len();
    if n == 0 {
        return Vec::new();
    }

    // Pre-compute nonzero flags for O(1) window queries via prefix sums
    let mut prefix_nonzero = vec![0usize; n + 1];
    for i in 0..n {
        prefix_nonzero[i + 1] = prefix_nonzero[i] + if counts[i] > 0.0 { 1 } else { 0 };
    }

    let mut periods: Vec<NonwearPeriod> = Vec::new();
    let mut i = 0;

    while i < n {
        if counts[i] > 0.0 {
            i += 1;
            continue;
        }

        let start_idx = i;
        let mut end_idx = i;
        let mut continuation = i;

        while continuation < n {
            if counts[continuation] == 0.0 {
                end_idx = continuation;
                continuation += 1;
                continue;
            }

            // Check spike tolerance using prefix sum (O(1) per query)
            let window_start = continuation.saturating_sub(WINDOW_SIZE);
            let window_end = (continuation + WINDOW_SIZE).min(n);

            let nonzero_count =
                prefix_nonzero[window_end] - prefix_nonzero[window_start];

            // Subtract 1 to exclude the current epoch (which we know is non-zero)
            // from the spike count — we're checking whether the *surrounding* window
            // has too many non-zero epochs, not the epoch itself.
            if nonzero_count.saturating_sub(1) > SPIKE_TOLERANCE {
                break;
            }

            continuation += 1;
        }

        if end_idx - start_idx + 1 >= MIN_PERIOD_LENGTH {
            periods.push(NonwearPeriod { start_idx, end_idx });
            i = end_idx + 1;
        } else {
            i += 1;
        }
    }

    // Merge adjacent periods (within 1 minute / 1 index)
    let merged = merge_periods(periods);

    // Convert to mask using slice fill (memset-optimized)
    let mut mask = vec![0u8; n];
    for period in &merged {
        let end = period.end_idx.min(n - 1);
        mask[period.start_idx..=end].fill(1);
    }

    mask
}

fn merge_periods(mut periods: Vec<NonwearPeriod>) -> Vec<NonwearPeriod> {
    if periods.is_empty() {
        return periods;
    }

    // Periods are expected sorted by start_idx (added in left-to-right scan order).
    // Defensive sort in case a future refactor breaks insertion order (negligible cost on small vec).
    debug_assert!(
        periods.windows(2).all(|w| w[0].start_idx <= w[1].start_idx),
        "merge_periods: input periods were not sorted by start_idx"
    );
    periods.sort_by_key(|p| p.start_idx);

    let mut merged: Vec<NonwearPeriod> = Vec::new();
    let mut current = NonwearPeriod {
        start_idx: periods[0].start_idx,
        end_idx: periods[0].end_idx,
    };

    for next in periods.into_iter().skip(1) {
        // Merge if gap <= 1 minute (1 index)
        if next.start_idx <= current.end_idx + 2 {
            current.end_idx = current.end_idx.max(next.end_idx);
        } else {
            merged.push(current);
            current = next;
        }
    }
    merged.push(current);

    merged
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_empty_input() {
        assert_eq!(detect(&[]), Vec::<u8>::new());
    }

    #[test]
    fn test_all_active_no_nonwear() {
        let counts = vec![100.0; 200];
        let result = detect(&counts);
        assert!(result.iter().all(|&v| v == 0), "All active = all wear");
    }

    #[test]
    fn test_long_zero_period() {
        // 100 zeros = nonwear (>= 90 min)
        let mut counts = vec![100.0; 10];
        counts.extend(vec![0.0; 100]);
        counts.extend(vec![100.0; 10]);

        let result = detect(&counts);
        // First 10 should be wear
        assert!(result[..10].iter().all(|&v| v == 0));
        // Middle 100 should be nonwear
        assert!(result[10..110].iter().all(|&v| v == 1));
        // Last 10 should be wear
        assert!(result[110..].iter().all(|&v| v == 0));
    }

    #[test]
    fn test_short_zero_period_not_nonwear() {
        // 80 zeros < 90 min threshold = not nonwear
        let mut counts = vec![100.0; 10];
        counts.extend(vec![0.0; 80]);
        counts.extend(vec![100.0; 10]);

        let result = detect(&counts);
        assert!(result.iter().all(|&v| v == 0), "Short zero period = wear");
    }

    #[test]
    fn test_single_epoch() {
        // Single zero → too short for nonwear
        assert_eq!(detect(&[0.0]), vec![0]);
        // Single non-zero → wear
        assert_eq!(detect(&[100.0]), vec![0]);
    }

    #[test]
    fn test_output_length_matches_input() {
        for n in [1, 50, 90, 91, 200] {
            let counts = vec![0.0; n];
            let result = detect(&counts);
            assert_eq!(result.len(), n, "Output length must match input for n={}", n);
        }
    }

    #[test]
    fn test_output_only_binary() {
        let mut counts = vec![100.0; 10];
        counts.extend(vec![0.0; 100]);
        counts.extend(vec![100.0; 10]);
        let result = detect(&counts);
        assert!(
            result.iter().all(|&v| v == 0 || v == 1),
            "Output must only contain 0 or 1"
        );
    }

    #[test]
    fn test_exact_90_is_nonwear() {
        // Exactly 90 zeros should be detected as nonwear (>= 90)
        let mut counts = vec![100.0; 10];
        counts.extend(vec![0.0; 90]);
        counts.extend(vec![100.0; 10]);
        let result = detect(&counts);
        assert!(result[10..100].iter().all(|&v| v == 1), "Exactly 90 zeros = nonwear");
        assert!(result[..10].iter().all(|&v| v == 0));
        assert!(result[100..].iter().all(|&v| v == 0));
    }

    #[test]
    fn test_89_zeros_not_nonwear() {
        // 89 zeros < 90 → not nonwear
        let mut counts = vec![100.0; 10];
        counts.extend(vec![0.0; 89]);
        counts.extend(vec![100.0; 10]);
        let result = detect(&counts);
        assert!(result.iter().all(|&v| v == 0), "89 zeros = wear");
    }

    #[test]
    fn test_all_zeros_is_nonwear() {
        // All zeros, 100 epochs → entire array is nonwear
        let counts = vec![0.0; 100];
        let result = detect(&counts);
        assert!(result.iter().all(|&v| v == 1), "All zeros (100) = nonwear");
    }

    #[test]
    fn test_spike_within_nonwear_tolerated() {
        // 90+ zeros with a single spike in the middle should still detect nonwear
        // because spike tolerance allows up to 2 non-zero minutes in a 30-min window
        let mut counts = vec![0.0; 100];
        counts[50] = 5.0; // single spike
        let result = detect(&counts);
        // The period should still be detected (spike tolerance)
        let nonwear_count: usize = result.iter().filter(|&&v| v == 1).count();
        assert!(nonwear_count >= 90, "Single spike should be tolerated: got {} nonwear", nonwear_count);
    }

    #[test]
    fn test_multiple_nonwear_periods() {
        // Two separate nonwear periods
        let mut counts = vec![0.0; 95];
        counts.extend(vec![100.0; 20]);
        counts.extend(vec![0.0; 95]);
        let result = detect(&counts);
        // First period: nonwear
        assert!(result[..95].iter().all(|&v| v == 1), "First period should be nonwear");
        // Gap: wear
        assert!(result[95..115].iter().all(|&v| v == 0), "Gap should be wear");
        // Second period: nonwear
        assert!(result[115..210].iter().all(|&v| v == 1), "Second period should be nonwear");
    }

    #[test]
    fn test_merge_adjacent_periods() {
        // Two zero periods separated by a single non-zero epoch
        // They should be handled by merge logic (gap <= 1)
        let mut counts = vec![0.0; 95];
        counts.push(5.0); // single non-zero gap
        counts.extend(vec![0.0; 95]);
        let result = detect(&counts);
        // Due to spike tolerance and merging, the whole area should be nonwear
        let nonwear_count: usize = result.iter().filter(|&&v| v == 1).count();
        assert!(nonwear_count > 95, "Adjacent periods should merge: got {} nonwear", nonwear_count);
    }
}
