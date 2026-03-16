use serde_json::Value;
use sleep_scoring_wasm::{choi, cole_kripke, sadeh};
use std::fs;

fn load_fixtures() -> Value {
    let data = fs::read_to_string("tests/fixtures/golden_tests.json").expect("fixture file");
    serde_json::from_str(&data).expect("parse JSON")
}

fn parse_f64_array(val: &Value) -> Vec<f64> {
    val.as_array()
        .unwrap()
        .iter()
        .map(|v| v.as_f64().unwrap())
        .collect()
}

fn parse_u8_array(val: &Value) -> Vec<u8> {
    val.as_array()
        .unwrap()
        .iter()
        .map(|v| v.as_u64().unwrap() as u8)
        .collect()
}

fn assert_choi_golden(fixture_key: &str) {
    let fixtures = load_fixtures();
    let section = &fixtures[fixture_key];
    let input = parse_f64_array(&section["input"]);
    let expected = parse_u8_array(&section["expected_output"]);

    let result = choi::detect(&input);

    assert_eq!(
        result.len(),
        expected.len(),
        "{}: output length mismatch: got {} expected {}",
        fixture_key,
        result.len(),
        expected.len()
    );

    let mismatches: Vec<usize> = result
        .iter()
        .zip(expected.iter())
        .enumerate()
        .filter(|(_, (r, e))| r != e)
        .map(|(i, _)| i)
        .collect();

    assert!(
        mismatches.is_empty(),
        "{}: mismatches at indices {:?} (first 10 shown)",
        fixture_key,
        &mismatches[..mismatches.len().min(10)]
    );
}

#[test]
fn test_sadeh_matches_python() {
    let data = fs::read_to_string("tests/fixtures/golden_tests.json").expect("fixture file");
    let fixtures: Value = serde_json::from_str(&data).expect("parse JSON");

    let input: Vec<f64> = fixtures["sadeh"]["input"]
        .as_array()
        .unwrap()
        .iter()
        .map(|v| v.as_f64().unwrap())
        .collect();
    let threshold = fixtures["sadeh"]["threshold"].as_f64().unwrap();
    let expected: Vec<u8> = fixtures["sadeh"]["expected_output"]
        .as_array()
        .unwrap()
        .iter()
        .map(|v| v.as_u64().unwrap() as u8)
        .collect();

    let result = sadeh::score(&input, threshold);

    assert_eq!(
        result.len(),
        expected.len(),
        "Sadeh output length mismatch: got {} expected {}",
        result.len(),
        expected.len()
    );

    let mismatches: Vec<usize> = result
        .iter()
        .zip(expected.iter())
        .enumerate()
        .filter(|(_, (r, e))| r != e)
        .map(|(i, _)| i)
        .collect();

    assert!(
        mismatches.is_empty(),
        "Sadeh mismatches at indices {:?} (first 10 shown)",
        &mismatches[..mismatches.len().min(10)]
    );
}

#[test]
fn test_cole_kripke_matches_python() {
    let data = fs::read_to_string("tests/fixtures/golden_tests.json").expect("fixture file");
    let fixtures: Value = serde_json::from_str(&data).expect("parse JSON");

    let input: Vec<f64> = fixtures["cole_kripke"]["input"]
        .as_array()
        .unwrap()
        .iter()
        .map(|v| v.as_f64().unwrap())
        .collect();
    let use_actilife = fixtures["cole_kripke"]["use_actilife_scaling"]
        .as_bool()
        .unwrap();
    let expected: Vec<u8> = fixtures["cole_kripke"]["expected_output"]
        .as_array()
        .unwrap()
        .iter()
        .map(|v| v.as_u64().unwrap() as u8)
        .collect();

    let result = cole_kripke::score(&input, use_actilife);

    assert_eq!(
        result.len(),
        expected.len(),
        "Cole-Kripke output length mismatch"
    );

    let mismatches: Vec<usize> = result
        .iter()
        .zip(expected.iter())
        .enumerate()
        .filter(|(_, (r, e))| r != e)
        .map(|(i, _)| i)
        .collect();

    assert!(
        mismatches.is_empty(),
        "Cole-Kripke mismatches at indices {:?} (first 10 shown)",
        &mismatches[..mismatches.len().min(10)]
    );
}

#[test]
fn test_choi_matches_python() {
    let data = fs::read_to_string("tests/fixtures/golden_tests.json").expect("fixture file");
    let fixtures: Value = serde_json::from_str(&data).expect("parse JSON");

    let input: Vec<f64> = fixtures["choi"]["input"]
        .as_array()
        .unwrap()
        .iter()
        .map(|v| v.as_f64().unwrap())
        .collect();
    let expected: Vec<u8> = fixtures["choi"]["expected_output"]
        .as_array()
        .unwrap()
        .iter()
        .map(|v| v.as_u64().unwrap() as u8)
        .collect();

    let result = choi::detect(&input);

    assert_eq!(
        result.len(),
        expected.len(),
        "Choi output length mismatch"
    );

    let mismatches: Vec<usize> = result
        .iter()
        .zip(expected.iter())
        .enumerate()
        .filter(|(_, (r, e))| r != e)
        .map(|(i, _)| i)
        .collect();

    assert!(
        mismatches.is_empty(),
        "Choi mismatches at indices {:?} (first 10 shown)",
        &mismatches[..mismatches.len().min(10)]
    );
}

#[test]
fn test_choi_spike_tolerance_3_breaks() {
    // 3 nonzero epochs in window exceeds spike tolerance (>2), splitting the zero region
    // so neither sub-region reaches 90 minutes => no nonwear detected
    assert_choi_golden("choi_spike_tolerance_3_breaks");
}

#[test]
fn test_choi_spike_tolerance_2_tolerated() {
    // 2 nonzero epochs in window is within spike tolerance (<=2),
    // so the entire 102-epoch region (including spike epochs) is marked nonwear
    assert_choi_golden("choi_spike_tolerance_2_tolerated");
}

#[test]
fn test_choi_no_merge_separate_periods() {
    // Two 95-epoch zero regions separated by 5 active epochs remain as
    // two separate nonwear periods — no merge step per Choi 2011
    assert_choi_golden("choi_no_merge_separate_periods");
}
