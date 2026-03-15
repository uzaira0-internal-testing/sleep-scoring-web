//! CSV parser for actigraphy data files.
//!
//! Handles:
//! - ActiGraph CSV (configurable header skip, auto-detect columns)
//! - GENEActiv raw CSV (7-column 100Hz format with header detection)
//! - Automatic column detection (datetime, axis, vector magnitude)
//! - Timestamp parsing to epoch milliseconds

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
        let bytes = line.as_bytes();
        bytes.len() >= 19
            && bytes[0..4].iter().all(|b| b.is_ascii_digit())
            && bytes[4] == b'-'
            && bytes[7] == b'-'
            && bytes[10] == b' '
    };

    let mut prev_line: Option<&str> = None;
    for (i, line) in content.lines().enumerate() {
        let stripped = line.trim();
        if stripped.is_empty() {
            continue;
        }
        if ts_prefix_chars(stripped) {
            let has_header = if let Some(prev) = prev_line {
                let prev_lower = prev.to_lowercase();
                ["timestamp", "x", "y", "z", "time", "lux", "temp"]
                    .iter()
                    .any(|kw| prev_lower.contains(kw))
            } else {
                false
            };
            return (i, has_header);
        }
        if i > 120 {
            break;
        }
        prev_line = Some(line);
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
            for part in line.split([',', ':', '\t']) {
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

/// Extract multiple fields by index from a line in a single pass.
/// `indices` must be sorted ascending. Returns fields in the order of `indices`.
/// Uses a fixed-size array to avoid heap allocation.
#[inline]
fn extract_fields<'a, const N: usize>(
    line: &'a str,
    sep: char,
    indices: &[usize; N],
) -> [Option<&'a str>; N] {
    let mut result = [None; N];
    let mut target = 0; // which index in `indices` we're looking for next
    for (col, field) in line.split(sep).enumerate() {
        if target >= N {
            break;
        }
        if col == indices[target] {
            result[target] = Some(field.trim());
            target += 1;
            // Check for duplicate indices at the same column
            while target < N && indices[target] == col {
                result[target] = result[target - 1];
                target += 1;
            }
        }
    }
    result
}

/// Count fields in a line without allocating.
#[inline]
fn count_fields(line: &str, sep: char) -> usize {
    if line.is_empty() {
        return 0;
    }
    line.split(sep).count()
}

/// Parse an ActiGraph-style CSV (with configurable header skip).
pub fn parse_actigraph_csv(content: &str, skip_rows: usize) -> Result<CsvParseResult, String> {
    // Skip header rows by tracking byte offset
    let mut byte_offset = 0usize;
    for _ in 0..skip_rows {
        match content[byte_offset..].find('\n') {
            Some(pos) => byte_offset += pos + 1,
            None => return Err("File has fewer lines than skip_rows".into()),
        }
    }

    let header_end = content[byte_offset..].find('\n')
        .ok_or("File has fewer lines than skip_rows")?;
    let header_line = &content[byte_offset..byte_offset + header_end];
    byte_offset += header_end + 1;

    let sep = if header_line.contains('\t') { '\t' } else { ',' };
    let headers: Vec<&str> = header_line.split(sep).map(|s| s.trim()).collect();
    let col_map = detect_columns(&headers);

    let datetime_col = col_map
        .datetime_col
        .or(col_map.date_col)
        .ok_or("No datetime/date column found")?;
    let axis_y_col = col_map.axis_y_col.ok_or("No axis_y/Axis1 column found")?;

    // Estimate row count for pre-allocation (count remaining newlines)
    let remaining = &content[byte_offset..];
    let est_rows = bytecount_newlines(remaining.as_bytes());

    let mut timestamps_ms = Vec::with_capacity(est_rows);
    let mut axis_y = Vec::with_capacity(est_rows);
    let mut axis_x = Vec::with_capacity(est_rows);
    let mut axis_z = Vec::with_capacity(est_rows);
    let mut vector_magnitude = Vec::with_capacity(est_rows);

    let has_separate_time = col_map.time_col.is_some() && col_map.date_col.is_some();
    let has_axis_x = col_map.axis_x_col.is_some();
    let has_axis_z = col_map.axis_z_col.is_some();
    let has_vm = col_map.vector_magnitude_col.is_some();

    // Build sorted column index map for single-pass extraction per line.
    // Each entry: (column_index, role). Sorted by column_index for sequential scan.
    const ROLE_DATETIME: u8 = 0;
    const ROLE_TIME: u8 = 1;
    const ROLE_AXIS_Y: u8 = 2;
    const ROLE_AXIS_X: u8 = 3;
    const ROLE_AXIS_Z: u8 = 4;
    const ROLE_VM: u8 = 5;

    let mut col_roles: Vec<(usize, u8)> = Vec::with_capacity(6);
    col_roles.push((datetime_col, ROLE_DATETIME));
    if has_separate_time {
        col_roles.push((col_map.time_col.unwrap(), ROLE_TIME));
    }
    col_roles.push((axis_y_col, ROLE_AXIS_Y));
    if let Some(c) = col_map.axis_x_col { col_roles.push((c, ROLE_AXIS_X)); }
    if let Some(c) = col_map.axis_z_col { col_roles.push((c, ROLE_AXIS_Z)); }
    if let Some(c) = col_map.vector_magnitude_col { col_roles.push((c, ROLE_VM)); }
    col_roles.sort_by_key(|&(idx, _)| idx);

    let max_col = col_roles.last().map_or(0, |&(idx, _)| idx);

    let mut ts_format = TimestampFormat::Unknown;
    let mut ts_buf = String::with_capacity(32);

    for line in remaining.lines() {
        let line = line.trim();
        if line.is_empty() {
            continue;
        }

        // Single-pass field extraction: walk the split iterator once,
        // picking up only the columns we need (in sorted order).
        let mut extracted: [Option<&str>; 6] = [None; 6];
        let mut target = 0;
        for (col, field) in line.split(sep).enumerate() {
            if target >= col_roles.len() { break; }
            if col == col_roles[target].0 {
                let role = col_roles[target].1 as usize;
                extracted[role] = Some(field.trim());
                target += 1;
            }
            if col >= max_col { break; }
        }

        // Parse timestamp
        let ts_ms = if has_separate_time {
            let date_part = match extracted[ROLE_DATETIME as usize] {
                Some(s) => s,
                None => continue,
            };
            let time_part = match extracted[ROLE_TIME as usize] {
                Some(s) => s,
                None => continue,
            };
            ts_buf.clear();
            ts_buf.push_str(date_part);
            ts_buf.push(' ');
            ts_buf.push_str(time_part);
            parse_timestamp_ms_with_hint(&ts_buf, &mut ts_format)
        } else {
            match extracted[ROLE_DATETIME as usize] {
                Some(s) => parse_timestamp_ms_with_hint(s, &mut ts_format),
                None => continue,
            }
        };

        let ts_ms = match ts_ms {
            Some(v) => v,
            None => continue,
        };

        // Parse axis_y (required)
        let y_str = match extracted[ROLE_AXIS_Y as usize] {
            Some(s) => s,
            None => continue,
        };

        timestamps_ms.push(ts_ms);
        axis_y.push(parse_f64(y_str));

        if has_axis_x {
            if let Some(s) = extracted[ROLE_AXIS_X as usize] {
                axis_x.push(parse_f64(s));
            }
        }
        if has_axis_z {
            if let Some(s) = extracted[ROLE_AXIS_Z as usize] {
                axis_z.push(parse_f64(s));
            }
        }
        if has_vm {
            if let Some(s) = extracted[ROLE_VM as usize] {
                vector_magnitude.push(parse_f64(s));
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

    // Skip to data start by tracking byte offset
    let mut byte_offset = 0usize;
    for _ in 0..data_start {
        match content[byte_offset..].find('\n') {
            Some(pos) => byte_offset += pos + 1,
            None => return Err("No data found in GENEActiv file".into()),
        }
    }
    let remaining = &content[byte_offset..];

    // Peek at first data line for separator and column count
    let first_data: &str = match remaining.lines().next() {
        Some(l) => l,
        None => return Err("No data found in GENEActiv file".into()),
    };
    let sep = if first_data.contains('\t') { '\t' } else { ',' };
    let num_cols = count_fields(first_data, sep);
    let is_raw = num_cols <= 7;

    // Estimate rows for pre-allocation
    let est_rows = bytecount_newlines(remaining.as_bytes());

    let mut timestamps_ms = Vec::with_capacity(est_rows);
    let mut axis_x = Vec::with_capacity(est_rows);
    let mut axis_y = Vec::with_capacity(est_rows);
    let mut axis_z = Vec::with_capacity(est_rows);

    let mut ts_format = TimestampFormat::Unknown;
    // Stack buffer for GENEActiv timestamp fixup (avoids heap allocation)
    let mut ts_buf = String::with_capacity(32);

    for line in remaining.lines() {
        let line = line.trim();
        if line.is_empty() {
            continue;
        }

        // Extract first 4 fields in a single pass
        let fields = extract_fields(line, sep, &[0, 1, 2, 3]);
        let field0 = match fields[0] { Some(s) => s, None => continue };
        let field1 = match fields[1] { Some(s) => s, None => continue };
        let field2 = match fields[2] { Some(s) => s, None => continue };
        let field3 = match fields[3] { Some(s) => s, None => continue };

        // Fix GENEActiv colon-millisecond in-place using buffer
        let ts_str = fix_geneactiv_timestamp_into(field0, &mut ts_buf);

        if let Some(ts) = parse_timestamp_ms_with_hint(ts_str, &mut ts_format) {
            timestamps_ms.push(ts);
            axis_x.push(parse_f64(field1));
            axis_y.push(parse_f64(field2));
            axis_z.push(parse_f64(field3));
        }
    }

    // Compute vector magnitude inline during collection
    let vector_magnitude: Vec<f64> = axis_x
        .iter()
        .zip(axis_y.iter())
        .zip(axis_z.iter())
        .map(|((&x, &y), &z)| (x * x + y * y + z * z).sqrt())
        .collect();

    Ok(CsvParseResult {
        timestamps_ms,
        axis_y,
        axis_x,
        axis_z,
        vector_magnitude,
        is_raw,
        sample_frequency: freq,
        header_rows_skipped: data_start as u32,
    })
}

/// Count newlines in a byte slice (fast estimate of row count).
fn bytecount_newlines(bytes: &[u8]) -> usize {
    bytes.iter().filter(|&&b| b == b'\n').count()
}

/// Fix GENEActiv colon-millisecond timestamps without heap allocation.
/// Returns a &str borrowing from either the input or the buffer.
fn fix_geneactiv_timestamp_into<'a>(s: &'a str, buf: &'a mut String) -> &'a str {
    let bytes = s.as_bytes();
    let len = bytes.len();
    if len >= 4
        && bytes[len - 4] == b':'
        && bytes[len - 3].is_ascii_digit()
        && bytes[len - 2].is_ascii_digit()
        && bytes[len - 1].is_ascii_digit()
    {
        buf.clear();
        buf.push_str(&s[..len - 4]);
        buf.push('.');
        buf.push_str(&s[len - 3..]);
        buf
    } else {
        s
    }
}

/// Fix GENEActiv colon-millisecond timestamps (allocating version for tests).
#[cfg(test)]
fn fix_geneactiv_timestamp(s: &str) -> String {
    let bytes = s.as_bytes();
    if bytes.len() >= 4 {
        let len = bytes.len();
        if bytes[len - 4] == b':'
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

/// Detected timestamp format for skipping fallback attempts.
#[derive(Clone, Copy, PartialEq)]
enum TimestampFormat {
    Unknown,
    Iso,
    Us,
}

/// Parse a timestamp string to milliseconds since Unix epoch.
/// Uses format hint to avoid trying both parsers on every row.
fn parse_timestamp_ms_with_hint(s: &str, hint: &mut TimestampFormat) -> Option<f64> {
    let s = s.trim().trim_matches('"');

    match *hint {
        TimestampFormat::Iso => return parse_iso_datetime(s),
        TimestampFormat::Us => return parse_us_datetime(s),
        TimestampFormat::Unknown => {}
    }

    if let Some(ms) = parse_iso_datetime(s) {
        *hint = TimestampFormat::Iso;
        return Some(ms);
    }

    if let Some(ms) = parse_us_datetime(s) {
        *hint = TimestampFormat::Us;
        return Some(ms);
    }

    None
}

/// Parse a timestamp string to milliseconds since Unix epoch (no hint).
#[cfg(test)]
fn parse_timestamp_ms(s: &str) -> Option<f64> {
    let s = s.trim().trim_matches('"');
    if let Some(ms) = parse_iso_datetime(s) {
        return Some(ms);
    }
    parse_us_datetime(s)
}

/// Parse ISO datetime directly from bytes without intermediate allocations.
fn parse_iso_datetime(s: &str) -> Option<f64> {
    // YYYY-MM-DD HH:MM:SS[.fff]
    let bytes = s.as_bytes();
    if bytes.len() < 19 {
        return None;
    }

    // Quick structural check
    if bytes[4] != b'-' || bytes[7] != b'-' || (bytes[10] != b' ' && bytes[10] != b'T') {
        return None;
    }

    let year = parse_int_fast(&bytes[0..4])? as i64;
    let month = parse_int_fast(&bytes[5..7])? as i64;
    let day = parse_int_fast(&bytes[8..10])? as i64;

    let (hour, min, sec, millis) = parse_time_from_bytes(&bytes[11..])?;

    let days = days_since_epoch(year, month, day)?;
    Some(
        days as f64 * 86400000.0
            + hour as f64 * 3600000.0
            + min as f64 * 60000.0
            + sec as f64 * 1000.0
            + millis,
    )
}

fn parse_us_datetime(s: &str) -> Option<f64> {
    // MM/DD/YYYY HH:MM:SS
    let bytes = s.as_bytes();
    if bytes.len() < 19 {
        return None;
    }

    // Find the space separating date and time
    let space_pos = memchr_byte(b' ', bytes)?;
    if space_pos < 8 {
        return None;
    }

    let date_part = &bytes[..space_pos];
    // Find slashes
    let slash1 = memchr_byte(b'/', date_part)?;
    let slash2 = slash1 + 1 + memchr_byte(b'/', &date_part[slash1 + 1..])?;

    let month = parse_int_fast(&date_part[..slash1])? as i64;
    let day = parse_int_fast(&date_part[slash1 + 1..slash2])? as i64;
    let year = parse_int_fast(&date_part[slash2 + 1..])? as i64;

    let (hour, min, sec, millis) = parse_time_from_bytes(&bytes[space_pos + 1..])?;

    let days = days_since_epoch(year, month, day)?;
    Some(
        days as f64 * 86400000.0
            + hour as f64 * 3600000.0
            + min as f64 * 60000.0
            + sec as f64 * 1000.0
            + millis,
    )
}

/// Parse time from bytes: HH:MM:SS[.fff]
#[inline]
fn parse_time_from_bytes(bytes: &[u8]) -> Option<(i64, i64, i64, f64)> {
    if bytes.len() < 8 {
        return None;
    }
    if bytes[2] != b':' || bytes[5] != b':' {
        return None;
    }

    let hour = parse_int_fast(&bytes[0..2])? as i64;
    let min = parse_int_fast(&bytes[3..5])? as i64;

    // Seconds may have fractional part
    let sec_start = 6;
    let mut sec_end = sec_start;
    while sec_end < bytes.len() && bytes[sec_end].is_ascii_digit() {
        sec_end += 1;
    }
    let sec = parse_int_fast(&bytes[sec_start..sec_end])? as i64;

    let millis = if sec_end < bytes.len() && bytes[sec_end] == b'.' {
        let frac_start = sec_end + 1;
        let mut frac_end = frac_start;
        while frac_end < bytes.len() && bytes[frac_end].is_ascii_digit() {
            frac_end += 1;
        }
        if frac_end > frac_start {
            let frac_val = parse_int_fast(&bytes[frac_start..frac_end])? as f64;
            let frac_len = (frac_end - frac_start) as i32;
            frac_val / 10.0_f64.powi(frac_len) * 1000.0
        } else {
            0.0
        }
    } else {
        0.0
    };

    Some((hour, min, sec, millis))
}

/// Fast integer parsing from ASCII bytes (no allocation, no error string).
#[inline]
fn parse_int_fast(bytes: &[u8]) -> Option<u32> {
    if bytes.is_empty() {
        return None;
    }
    let mut result: u32 = 0;
    for &b in bytes {
        if !b.is_ascii_digit() {
            return None;
        }
        result = result.checked_mul(10)?.checked_add((b - b'0') as u32)?;
    }
    Some(result)
}

/// Find first occurrence of a byte in a slice.
#[inline]
fn memchr_byte(needle: u8, haystack: &[u8]) -> Option<usize> {
    haystack.iter().position(|&b| b == needle)
}

/// Days since Unix epoch (1970-01-01).
fn days_since_epoch(year: i64, month: i64, day: i64) -> Option<i64> {
    if !(1..=12).contains(&month) || !(1..=31).contains(&day) {
        return None;
    }
    let (y, m) = if month <= 2 {
        (year - 1, month + 12)
    } else {
        (year, month)
    };
    let days = 365 * y + y / 4 - y / 100 + y / 400 + (153 * (m - 3) + 2) / 5 + day - 719469;
    Some(days)
}

#[inline]
fn parse_f64(s: &str) -> f64 {
    s.trim().trim_matches('"').parse::<f64>().unwrap_or(0.0)
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_parse_iso_datetime() {
        let ms = parse_timestamp_ms("2024-01-01 00:00:00").unwrap();
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

    #[test]
    fn test_detect_frequency_sample_rate() {
        let header = "Device Type,GENEActiv\nSample Rate,50 hz\nData:";
        assert_eq!(detect_frequency(header), 50);
    }

    #[test]
    fn test_detect_frequency_default() {
        let header = "Device Type,GENEActiv\nSome Other Header\n";
        assert_eq!(detect_frequency(header), 100); // Default
    }

    #[test]
    fn test_is_geneactiv_empty() {
        assert!(!is_geneactiv(""));
    }

    #[test]
    fn test_is_geneactiv_case_insensitive() {
        assert!(is_geneactiv("device type,GENEACTIV\n"));
        assert!(is_geneactiv("Device Type,GeneActiv\n"));
    }

    #[test]
    fn test_parse_us_datetime() {
        let ms = parse_timestamp_ms("01/01/2024 00:00:00").unwrap();
        assert!((ms - 1704067200000.0).abs() < 1000.0);
    }

    #[test]
    fn test_parse_timestamp_invalid() {
        assert!(parse_timestamp_ms("not a date").is_none());
        assert!(parse_timestamp_ms("").is_none());
        assert!(parse_timestamp_ms("2024").is_none());
    }

    #[test]
    fn test_parse_actigraph_csv_basic() {
        let csv = "Header line 1\nHeader line 2\nDatetime,Axis1,Axis2,Axis3\n\
                   2024-01-01 00:00:00,100,50,25\n\
                   2024-01-01 00:01:00,200,75,30\n";
        let result = parse_actigraph_csv(csv, 2).unwrap();
        assert_eq!(result.axis_y.len(), 2);
        assert_eq!(result.axis_y[0], 100.0);
        assert_eq!(result.axis_y[1], 200.0);
        assert_eq!(result.axis_x[0], 50.0);
        assert_eq!(result.axis_z[0], 25.0);
        assert!(!result.is_raw);
    }

    #[test]
    fn test_parse_actigraph_csv_tab_separated() {
        let csv = "Datetime\tAxis1\n\
                   2024-01-01 00:00:00\t100\n\
                   2024-01-01 00:01:00\t200\n";
        let result = parse_actigraph_csv(csv, 0).unwrap();
        assert_eq!(result.axis_y.len(), 2);
        assert_eq!(result.axis_y[0], 100.0);
        assert_eq!(result.axis_y[1], 200.0);
    }

    #[test]
    fn test_parse_actigraph_csv_empty_lines_skipped() {
        let csv = "Datetime,Axis1\n\
                   2024-01-01 00:00:00,100\n\
                   \n\
                   2024-01-01 00:01:00,200\n";
        let result = parse_actigraph_csv(csv, 0).unwrap();
        assert_eq!(result.axis_y.len(), 2);
    }

    #[test]
    fn test_parse_actigraph_csv_with_vm_column() {
        let csv = "Datetime,Axis1,Vector Magnitude\n\
                   2024-01-01 00:00:00,100,150.5\n\
                   2024-01-01 00:01:00,200,250.0\n";
        let result = parse_actigraph_csv(csv, 0).unwrap();
        assert_eq!(result.vector_magnitude.len(), 2);
        assert_eq!(result.vector_magnitude[0], 150.5);
    }

    #[test]
    fn test_parse_actigraph_csv_no_datetime_column() {
        let csv = "Axis1,Axis2\n100,50\n200,75\n";
        let result = parse_actigraph_csv(csv, 0);
        assert!(result.is_err());
    }

    #[test]
    fn test_parse_actigraph_csv_no_axis1_column() {
        let csv = "Datetime,SomeOther\n2024-01-01 00:00:00,50\n";
        let result = parse_actigraph_csv(csv, 0);
        assert!(result.is_err());
    }

    #[test]
    fn test_parse_actigraph_csv_too_many_skip_rows() {
        let csv = "one line\n";
        let result = parse_actigraph_csv(csv, 5);
        assert!(result.is_err());
    }

    #[test]
    fn test_parse_actigraph_csv_date_time_separate_columns() {
        let csv = "Date,Time,Axis1\n\
                   01/15/2024,10:30:00,100\n\
                   01/15/2024,10:31:00,200\n";
        let result = parse_actigraph_csv(csv, 0).unwrap();
        assert_eq!(result.axis_y.len(), 2);
    }

    #[test]
    fn test_fix_geneactiv_timestamp_no_change() {
        // Already correct format
        assert_eq!(
            fix_geneactiv_timestamp("2025-06-12 13:20:18.500"),
            "2025-06-12 13:20:18.500"
        );
    }

    #[test]
    fn test_fix_geneactiv_timestamp_short_string() {
        // Too short to match the pattern
        assert_eq!(fix_geneactiv_timestamp("abc"), "abc");
    }

    #[test]
    fn test_extract_fields_basic() {
        let result = extract_fields("a,b,c,d", ',', &[0, 2, 3]);
        assert_eq!(result[0], Some("a"));
        assert_eq!(result[1], Some("c"));
        assert_eq!(result[2], Some("d"));
    }

    #[test]
    fn test_extract_fields_out_of_range() {
        let result = extract_fields("a,b", ',', &[0, 5]);
        assert_eq!(result[0], Some("a"));
        assert_eq!(result[1], None);
    }

    #[test]
    fn test_count_fields_empty() {
        assert_eq!(count_fields("", ','), 0);
    }

    #[test]
    fn test_count_fields_basic() {
        assert_eq!(count_fields("a,b,c", ','), 3);
        assert_eq!(count_fields("a\tb\tc", '\t'), 3);
    }

    #[test]
    fn test_parse_f64_invalid() {
        assert_eq!(parse_f64("not_a_number"), 0.0);
        assert_eq!(parse_f64(""), 0.0);
    }

    #[test]
    fn test_parse_f64_with_quotes() {
        assert_eq!(parse_f64("\"42.5\""), 42.5);
    }

    #[test]
    fn test_days_since_epoch_invalid() {
        assert!(days_since_epoch(2024, 0, 1).is_none());  // month < 1
        assert!(days_since_epoch(2024, 13, 1).is_none()); // month > 12
        assert!(days_since_epoch(2024, 1, 0).is_none());  // day < 1
        assert!(days_since_epoch(2024, 1, 32).is_none()); // day > 31
    }

    #[test]
    fn test_find_geneactiv_data_start_with_header() {
        let content = "Device Type,GENEActiv\nMeasurement Frequency,100 Hz\n\
                       Timestamp,X,Y,Z,Lux,Button,Temp\n\
                       2025-01-01 00:00:00.000,0.1,0.2,0.3,100,0,25.0\n";
        let (start, has_header) = find_geneactiv_data_start(content);
        assert_eq!(start, 3);
        assert!(has_header);
    }

    #[test]
    fn test_parse_geneactiv_csv_basic() {
        let content = "Device Type,GENEActiv\n\
                       Measurement Frequency,100 Hz\n\
                       Timestamp,X,Y,Z,Lux,Button,Temp\n\
                       2025-01-01 00:00:00.000,0.1,0.2,0.3,100,0,25.0\n\
                       2025-01-01 00:00:00.010,0.4,0.5,0.6,100,0,25.0\n";
        let result = parse_geneactiv_csv(content).unwrap();
        assert_eq!(result.axis_x.len(), 2);
        assert_eq!(result.axis_x[0], 0.1);
        assert_eq!(result.axis_y[0], 0.2);
        assert_eq!(result.axis_z[0], 0.3);
        assert!(result.is_raw);
        assert_eq!(result.sample_frequency, 100);
    }

    #[test]
    fn test_parse_int_fast_basic() {
        assert_eq!(parse_int_fast(b"123"), Some(123));
        assert_eq!(parse_int_fast(b"0"), Some(0));
        assert_eq!(parse_int_fast(b""), None);
        assert_eq!(parse_int_fast(b"abc"), None);
        assert_eq!(parse_int_fast(b"12a3"), None);
    }

    #[test]
    fn test_memchr_byte_basic() {
        assert_eq!(memchr_byte(b',', b"hello,world"), Some(5));
        assert_eq!(memchr_byte(b'x', b"hello"), None);
        assert_eq!(memchr_byte(b'h', b"hello"), Some(0));
    }
}
