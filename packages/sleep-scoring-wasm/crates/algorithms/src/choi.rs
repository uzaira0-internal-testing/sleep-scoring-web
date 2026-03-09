/// Choi (2011) nonwear detection algorithm.
///
/// Ports the Python implementation exactly:
/// - Finds consecutive zero-count periods
/// - Allows spikes of up to spike_tolerance (2) non-zero minutes within a window
/// - Minimum period length: 90 minutes
/// - Window size for spike checking: 30 minutes
/// - Merges adjacent periods within 1 minute

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

            // Check spike tolerance in surrounding window
            let window_start = if continuation >= WINDOW_SIZE {
                continuation - WINDOW_SIZE
            } else {
                0
            };
            let window_end = (continuation + WINDOW_SIZE).min(n);

            let nonzero_count = counts[window_start..window_end]
                .iter()
                .filter(|&&v| v > 0.0)
                .count();

            if nonzero_count > SPIKE_TOLERANCE {
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

    // Convert to mask
    let mut mask = vec![0u8; n];
    for period in &merged {
        for idx in period.start_idx..=period.end_idx.min(n - 1) {
            mask[idx] = 1;
        }
    }

    mask
}

fn merge_periods(mut periods: Vec<NonwearPeriod>) -> Vec<NonwearPeriod> {
    if periods.is_empty() {
        return periods;
    }

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
}
