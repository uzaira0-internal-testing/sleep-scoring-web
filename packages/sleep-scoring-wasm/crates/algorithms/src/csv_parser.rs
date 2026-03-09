/// CSV parser for actigraphy data files.
///
/// Handles:
/// - ActiGraph CSV (configurable header skip, auto-detect columns)
/// - GENEActiv raw CSV (7-column 100Hz format with header detection)
/// - Automatic column detection (datetime, axis, vector magnitude)
/// - Timestamp parsing to epoch milliseconds

use crate::types::CsvParseResult;

/// Detect if a CSV file is GENEActiv format by checking first line.
pub fn is_geneactiv(content: &str) -> bool {
    if let Some(first_line) = content.lines().next() {
        let lower = first_line.to_lowercase();
        lower.contains("geneactiv") && lower.contains("device")
    } else {
        false
    }
}

/// Find where data starts in a GENEActiv file.
/// Returns (data_start_line, has_header_row).
pub fn find_geneactiv_data_start(content: &str) -> (usize, bool) {
    let ts_prefix_chars = |line: &str| -> bool {
        // Check if line starts with a timestamp: YYYY-MM-DD HH:MM:SS
        let bytes = line.as_bytes();
        bytes.len() >= 19
            && bytes[0..4].iter().all(|b| b.is_ascii_digit())
            && bytes[4] == b'-'
            && bytes[7] == b'-'
            && bytes[10] == b' '
    };

    let lines: Vec<&str> = content.lines().collect();

    for (i, line) in lines.iter().enumerate() {
        let stripped = line.trim();
        if stripped.is_empty() {
            continue;
        }
        if ts_prefix_chars(stripped) {
            // Check if previous line is a header
            let has_header = if i > 0 {
                let prev = lines[i - 1].to_lowercase();
                ["timestamp", "x", "y", "z", "time", "lux", "temp"]
                    .iter()
                    .any(|kw| prev.contains(kw))
            } else {
                false
            };
            return (i, has_header);
        }
        if i > 120 {
            break;
        }
    }
    (100, false) // Default fallback
}

/// Detect measurement frequency from GENEActiv header.
pub fn detect_frequency(content: &str) -> u32 {
    for (i, line) in content.lines().enumerate() {
        if i > 120 {
            break;
        }
        let lower = line.to_lowercase();
        if lower.contains("measurement frequency") || lower.contains("sample rate") {
            // Extract number
            for part in line.split(|c: char| c == ',' || c == ':' || c == '\t') {
                let trimmed = part.trim().trim_end_matches(" hz").trim_end_matches("hz");
                if let Ok(freq) = trimmed.parse::<u32>() {
                    if freq > 0 {
                        return freq;
                    }
                }
            }
        }
    }
    100 // Default GENEActiv frequency
}

/// Column indices detected from header row.
#[derive(Debug, Default)]
struct ColumnMap {
    datetime_col: Option<usize>,
    date_col: Option<usize>,
    time_col: Option<usize>,
    axis_y_col: Option<usize>,
    axis_x_col: Option<usize>,
    axis_z_col: Option<usize>,
    vector_magnitude_col: Option<usize>,
}

/// Detect column indices from a header row.
fn detect_columns(headers: &[&str]) -> ColumnMap {
    let mut map = ColumnMap::default();

    for (i, col) in headers.iter().enumerate() {
        let lower = col.to_lowercase().trim().to_string();
        match lower.as_str() {
            "datetime" | "timestamp" => map.datetime_col = Some(i),
            "date" => map.date_col = Some(i),
            "time" => map.time_col = Some(i),
            "axis1" | "axis_y" | "y" | "axis 1" | "y-axis" => map.axis_y_col = Some(i),
            "axis2" | "axis_x" | "x" | "axis 2" => map.axis_x_col = Some(i),
            "axis3" | "axis_z" | "z" | "axis 3" => map.axis_z_col = Some(i),
            _ => {
                let l = lower.as_str();
                if l.contains("vector") || l.contains("magnitude") || l == "vm" || l == "svm" {
                    map.vector_magnitude_col = Some(i);
                }
                if map.datetime_col.is_none() && l.contains("date") && !l.contains("time") {
                    map.date_col = Some(i);
                }
                if map.datetime_col.is_none() && l.contains("time") && !l.contains("date") {
                    map.time_col = Some(i);
                }
            }
        }
    }

    map
}

/// Parse an ActiGraph-style CSV (with configurable header skip).
pub fn parse_actigraph_csv(content: &str, skip_rows: usize) -> Result<CsvParseResult, String> {
    let lines: Vec<&str> = content.lines().collect();
    if lines.len() <= skip_rows {
        return Err("File has fewer lines than skip_rows".into());
    }

    // Header row is at skip_rows index
    let header_line = lines[skip_rows];
    let sep = if header_line.contains('\t') { '\t' } else { ',' };
    let headers: Vec<&str> = header_line.split(sep).map(|s| s.trim()).collect();
    let col_map = detect_columns(&headers);

    let datetime_col = col_map
        .datetime_col
        .or(col_map.date_col)
        .ok_or("No datetime/date column found")?;
    let axis_y_col = col_map.axis_y_col.ok_or("No axis_y/Axis1 column found")?;

    let mut timestamps_ms = Vec::new();
    let mut axis_y = Vec::new();
    let mut axis_x = Vec::new();
    let mut axis_z = Vec::new();
    let mut vector_magnitude = Vec::new();

    for line in &lines[skip_rows + 1..] {
        let line = line.trim();
        if line.is_empty() {
            continue;
        }
        let fields: Vec<&str> = line.split(sep).map(|s| s.trim()).collect();
        if fields.len() <= datetime_col || fields.len() <= axis_y_col {
            continue;
        }

        // Parse timestamp
        let ts_str = if let Some(time_col) = col_map.time_col {
            if col_map.date_col.is_some() && time_col < fields.len() {
                format!("{} {}", fields[datetime_col], fields[time_col])
            } else {
                fields[datetime_col].to_string()
            }
        } else {
            fields[datetime_col].to_string()
        };

        let ts_ms = parse_timestamp_ms(&ts_str);
        if ts_ms.is_none() {
            continue;
        }
        timestamps_ms.push(ts_ms.unwrap());

        // Parse axis values
        axis_y.push(parse_f64(fields[axis_y_col]));

        if let Some(col) = col_map.axis_x_col {
            if col < fields.len() {
                axis_x.push(parse_f64(fields[col]));
            }
        }
        if let Some(col) = col_map.axis_z_col {
            if col < fields.len() {
                axis_z.push(parse_f64(fields[col]));
            }
        }
        if let Some(col) = col_map.vector_magnitude_col {
            if col < fields.len() {
                vector_magnitude.push(parse_f64(fields[col]));
            }
        }
    }

    // Pad axis_x, axis_z if not present
    let n = axis_y.len();
    if axis_x.len() != n {
        axis_x = vec![0.0; n];
    }
    if axis_z.len() != n {
        axis_z = vec![0.0; n];
    }
    // Compute vector magnitude if not present
    if vector_magnitude.len() != n {
        vector_magnitude = axis_x
            .iter()
            .zip(axis_y.iter())
            .zip(axis_z.iter())
            .map(|((&x, &y), &z)| (x * x + y * y + z * z).sqrt())
            .collect();
    }

    Ok(CsvParseResult {
        timestamps_ms,
        axis_y,
        axis_x,
        axis_z,
        vector_magnitude,
        is_raw: false,
        sample_frequency: 0,
        header_rows_skipped: skip_rows as u32,
    })
}

/// Parse a GENEActiv raw CSV (headerless 7-column format).
pub fn parse_geneactiv_csv(content: &str) -> Result<CsvParseResult, String> {
    let (data_start, _has_header) = find_geneactiv_data_start(content);
    let freq = detect_frequency(content);

    let lines: Vec<&str> = content.lines().collect();
    let start = data_start;

    if lines.len() <= start {
        return Err("No data found in GENEActiv file".into());
    }

    // Detect separator from first data line
    let first_data = lines[start];
    let sep = if first_data.contains('\t') { '\t' } else { ',' };

    // Count columns to determine format
    let num_cols = first_data.split(sep).count();
    let is_raw = num_cols <= 7;

    let mut timestamps_ms = Vec::new();
    let mut axis_x = Vec::new();
    let mut axis_y = Vec::new();
    let mut axis_z = Vec::new();

    for line in &lines[start..] {
        let line = line.trim();
        if line.is_empty() {
            continue;
        }
        let fields: Vec<&str> = line.split(sep).map(|s| s.trim()).collect();
        if fields.len() < 4 {
            continue;
        }

        // Fix GENEActiv colon-millisecond: "2025-06-12 13:20:18:000" → "2025-06-12 13:20:18.000"
        let ts_str = fix_geneactiv_timestamp(fields[0]);

        if let Some(ts) = parse_timestamp_ms(&ts_str) {
            timestamps_ms.push(ts);
            axis_x.push(parse_f64(fields[1]));
            axis_y.push(parse_f64(fields[2]));
            axis_z.push(parse_f64(fields[3]));
        }
    }

    let n = axis_y.len();
    let vector_magnitude: Vec<f64> = (0..n)
        .map(|i| {
            let x = axis_x[i];
            let y = axis_y[i];
            let z = axis_z[i];
            (x * x + y * y + z * z).sqrt()
        })
        .collect();

    Ok(CsvParseResult {
        timestamps_ms,
        axis_y,
        axis_x,
        axis_z,
        vector_magnitude,
        is_raw,
        sample_frequency: freq,
        header_rows_skipped: start as u32,
    })
}

/// Fix GENEActiv colon-millisecond timestamps.
fn fix_geneactiv_timestamp(s: &str) -> String {
    // Replace last colon followed by 3 digits with period
    let bytes = s.as_bytes();
    if bytes.len() >= 4 {
        let len = bytes.len();
        // Check if last 4 chars are :DDD
        if len >= 4
            && bytes[len - 4] == b':'
            && bytes[len - 3].is_ascii_digit()
            && bytes[len - 2].is_ascii_digit()
            && bytes[len - 1].is_ascii_digit()
        {
            let mut result = s[..len - 4].to_string();
            result.push('.');
            result.push_str(&s[len - 3..]);
            return result;
        }
    }
    s.to_string()
}

/// Parse a timestamp string to milliseconds since Unix epoch.
fn parse_timestamp_ms(s: &str) -> Option<f64> {
    // Try common formats: "YYYY-MM-DD HH:MM:SS", "YYYY-MM-DD HH:MM:SS.fff"
    // Also: "MM/DD/YYYY HH:MM:SS"
    let s = s.trim().trim_matches('"');

    // Try ISO-like format first
    if let Some(ms) = parse_iso_datetime(s) {
        return Some(ms);
    }

    // Try US format: MM/DD/YYYY HH:MM:SS
    if let Some(ms) = parse_us_datetime(s) {
        return Some(ms);
    }

    None
}

fn parse_iso_datetime(s: &str) -> Option<f64> {
    // YYYY-MM-DD HH:MM:SS[.fff]
    let parts: Vec<&str> = s.splitn(2, |c| c == ' ' || c == 'T').collect();
    if parts.len() != 2 {
        return None;
    }

    let date_parts: Vec<&str> = parts[0].split('-').collect();
    if date_parts.len() != 3 {
        return None;
    }

    let year: i64 = date_parts[0].parse().ok()?;
    let month: i64 = date_parts[1].parse().ok()?;
    let day: i64 = date_parts[2].parse().ok()?;

    let (hour, min, sec, millis) = parse_time_parts(parts[1])?;

    let days = days_since_epoch(year, month, day)?;
    let ms = days as f64 * 86400000.0
        + hour as f64 * 3600000.0
        + min as f64 * 60000.0
        + sec as f64 * 1000.0
        + millis;

    Some(ms)
}

fn parse_us_datetime(s: &str) -> Option<f64> {
    // MM/DD/YYYY HH:MM:SS
    let parts: Vec<&str> = s.splitn(2, ' ').collect();
    if parts.len() != 2 {
        return None;
    }

    let date_parts: Vec<&str> = parts[0].split('/').collect();
    if date_parts.len() != 3 {
        return None;
    }

    let month: i64 = date_parts[0].parse().ok()?;
    let day: i64 = date_parts[1].parse().ok()?;
    let year: i64 = date_parts[2].parse().ok()?;

    let (hour, min, sec, millis) = parse_time_parts(parts[1])?;

    let days = days_since_epoch(year, month, day)?;
    let ms = days as f64 * 86400000.0
        + hour as f64 * 3600000.0
        + min as f64 * 60000.0
        + sec as f64 * 1000.0
        + millis;

    Some(ms)
}

fn parse_time_parts(s: &str) -> Option<(i64, i64, i64, f64)> {
    // HH:MM:SS[.fff] or HH:MM:SS
    let time_parts: Vec<&str> = s.split(':').collect();
    if time_parts.len() < 3 {
        return None;
    }
    let hour: i64 = time_parts[0].parse().ok()?;
    let min: i64 = time_parts[1].parse().ok()?;

    // Seconds may have fractional part
    let sec_parts: Vec<&str> = time_parts[2].split('.').collect();
    let sec: i64 = sec_parts[0].parse().ok()?;
    let millis: f64 = if sec_parts.len() > 1 {
        let frac = sec_parts[1];
        let frac_val: f64 = frac.parse().ok()?;
        frac_val / 10.0_f64.powi(frac.len() as i32) * 1000.0
    } else {
        0.0
    };

    Some((hour, min, sec, millis))
}

/// Days since Unix epoch (1970-01-01).
fn days_since_epoch(year: i64, month: i64, day: i64) -> Option<i64> {
    // Simple algorithm for converting date to days since epoch
    if month < 1 || month > 12 || day < 1 || day > 31 {
        return None;
    }
    // Adjust for months
    let (y, m) = if month <= 2 {
        (year - 1, month + 12)
    } else {
        (year, month)
    };

    let days = 365 * y + y / 4 - y / 100 + y / 400 + (153 * (m - 3) + 2) / 5 + day - 719469;
    Some(days)
}

fn parse_f64(s: &str) -> f64 {
    s.trim().trim_matches('"').parse::<f64>().unwrap_or(0.0)
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_parse_iso_datetime() {
        let ms = parse_timestamp_ms("2024-01-01 00:00:00").unwrap();
        // 2024-01-01 = day 19723 since epoch
        assert!((ms - 1704067200000.0).abs() < 1000.0);
    }

    #[test]
    fn test_parse_iso_with_millis() {
        let ms = parse_timestamp_ms("2024-01-01 00:00:00.500").unwrap();
        assert!((ms - 1704067200500.0).abs() < 1.0);
    }

    #[test]
    fn test_fix_geneactiv_timestamp() {
        assert_eq!(
            fix_geneactiv_timestamp("2025-06-12 13:20:18:000"),
            "2025-06-12 13:20:18.000"
        );
        assert_eq!(
            fix_geneactiv_timestamp("2025-06-12 13:20:18.000"),
            "2025-06-12 13:20:18.000"
        );
    }

    #[test]
    fn test_detect_geneactiv() {
        assert!(is_geneactiv("Device Type,GENEActiv\n"));
        assert!(!is_geneactiv("Epoch-by-Epoch Data\n"));
    }

    #[test]
    fn test_detect_frequency() {
        let header = "Device Type,GENEActiv\nMeasurement Frequency,100 Hz\nData:";
        assert_eq!(detect_frequency(header), 100);
    }
}
