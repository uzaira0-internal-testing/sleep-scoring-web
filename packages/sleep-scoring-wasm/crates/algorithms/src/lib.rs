pub mod choi;
pub mod cole_kripke;
pub mod csv_parser;
pub mod epoching;
pub mod sadeh;
pub mod types;

use wasm_bindgen::prelude::*;

/// Score activity data using Sadeh (1994) algorithm.
///
/// Input: Float64Array of Axis1 activity counts
/// Output: Uint8Array of 1 (sleep) / 0 (wake) per epoch
#[wasm_bindgen(js_name = "scoreSadeh")]
pub fn score_sadeh(activity: &[f64], threshold: f64) -> Vec<u8> {
    sadeh::score(activity, threshold)
}

/// Score activity data using Cole-Kripke (1992) algorithm.
///
/// Input: Float64Array of Axis1 activity counts
/// Output: Uint8Array of 1 (sleep) / 0 (wake) per epoch
#[wasm_bindgen(js_name = "scoreColeKripke")]
pub fn score_cole_kripke(activity: &[f64], use_actilife_scaling: bool) -> Vec<u8> {
    cole_kripke::score(activity, use_actilife_scaling)
}

/// Detect nonwear periods using Choi (2011) algorithm.
///
/// Input: Float64Array of activity counts (vector magnitude recommended)
/// Output: Uint8Array of 1 (nonwear) / 0 (wear) per epoch
#[wasm_bindgen(js_name = "detectNonwear")]
pub fn detect_nonwear(counts: &[f64]) -> Vec<u8> {
    choi::detect(counts)
}

/// Parse an ActiGraph-style CSV file.
///
/// Returns a JsValue (serialized CsvParseResult).
#[wasm_bindgen(js_name = "parseActigraphCsv")]
pub fn parse_actigraph_csv(content: &str, skip_rows: u32) -> Result<JsValue, JsValue> {
    let result = csv_parser::parse_actigraph_csv(content, skip_rows as usize)
        .map_err(|e| JsValue::from_str(&e))?;
    serde_wasm_bindgen::to_value(&result).map_err(|e| JsValue::from_str(&e.to_string()))
}

/// Parse a GENEActiv CSV file (raw or epoch format).
///
/// Returns a JsValue (serialized CsvParseResult).
#[wasm_bindgen(js_name = "parseGeneactivCsv")]
pub fn parse_geneactiv_csv(content: &str) -> Result<JsValue, JsValue> {
    let result = csv_parser::parse_geneactiv_csv(content)
        .map_err(|e| JsValue::from_str(&e))?;
    serde_wasm_bindgen::to_value(&result).map_err(|e| JsValue::from_str(&e.to_string()))
}

/// Check if CSV content is GENEActiv format.
#[wasm_bindgen(js_name = "isGeneactivFormat")]
pub fn is_geneactiv_format(content: &str) -> bool {
    csv_parser::is_geneactiv(content)
}

/// Epoch raw high-frequency data to 60-second counts.
///
/// Returns a JsValue (serialized EpochResult).
#[wasm_bindgen(js_name = "epochRawData")]
pub fn epoch_raw_data(
    timestamps_ms: &[f64],
    axis_x: &[f64],
    axis_y: &[f64],
    axis_z: &[f64],
    sample_freq: u32,
) -> Result<JsValue, JsValue> {
    let result = epoching::epoch_raw_data(timestamps_ms, axis_x, axis_y, axis_z, sample_freq);
    serde_wasm_bindgen::to_value(&result).map_err(|e| JsValue::from_str(&e.to_string()))
}
