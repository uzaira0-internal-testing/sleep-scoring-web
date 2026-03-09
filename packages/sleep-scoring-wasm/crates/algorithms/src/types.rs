use serde::{Deserialize, Serialize};

/// Result of CSV parsing: detected columns and parsed data.
#[derive(Debug, Serialize, Deserialize)]
pub struct CsvParseResult {
    /// Epoch timestamps as milliseconds since Unix epoch
    pub timestamps_ms: Vec<f64>,
    /// Y-axis (Axis1) activity counts
    pub axis_y: Vec<f64>,
    /// X-axis activity counts (if available)
    pub axis_x: Vec<f64>,
    /// Z-axis activity counts (if available)
    pub axis_z: Vec<f64>,
    /// Vector magnitude (computed or from column)
    pub vector_magnitude: Vec<f64>,
    /// Whether this is raw high-frequency data needing epoching
    pub is_raw: bool,
    /// Detected sample frequency (Hz) for raw data
    pub sample_frequency: u32,
    /// Number of header rows skipped
    pub header_rows_skipped: u32,
}

/// Result of epoching raw data into 60-second epochs.
#[derive(Debug, Serialize, Deserialize)]
pub struct EpochResult {
    /// Epoch timestamps as milliseconds since Unix epoch
    pub timestamps_ms: Vec<f64>,
    /// Y-axis epoch counts
    pub axis_y: Vec<f64>,
    /// X-axis epoch counts
    pub axis_x: Vec<f64>,
    /// Z-axis epoch counts
    pub axis_z: Vec<f64>,
    /// Vector magnitude per epoch
    pub vector_magnitude: Vec<f64>,
}
