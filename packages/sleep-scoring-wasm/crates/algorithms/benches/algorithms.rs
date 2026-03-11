use criterion::{criterion_group, criterion_main, BenchmarkId, Criterion, Throughput};
use std::hint::black_box;

use sleep_scoring_wasm::choi;
use sleep_scoring_wasm::cole_kripke;
use sleep_scoring_wasm::csv_parser;
use sleep_scoring_wasm::sadeh;

// ---------------------------------------------------------------------------
// Data generators
// ---------------------------------------------------------------------------

/// Synthetic activity data: alternating low/high blocks to mimic real sleep/wake.
fn make_activity(n: usize) -> Vec<f64> {
    let mut data = Vec::with_capacity(n);
    for i in 0..n {
        // 30-minute blocks: low (0-20) then high (50-300)
        let block = (i / 30) % 2;
        let base = if block == 0 { 5.0 } else { 150.0 };
        // Add some variation based on index
        let jitter = ((i * 7 + 13) % 41) as f64;
        data.push(base + jitter);
    }
    data
}

/// Choi-style data: mostly zeros with occasional activity bursts and short spikes.
fn make_choi_data(n: usize) -> Vec<f64> {
    let mut data = vec![0.0; n];
    // Add activity bursts (wear periods)
    let burst_len = 60; // 1-hour bursts
    let gap = 200; // every ~200 epochs
    let mut pos = 0;
    while pos + burst_len < n {
        for j in 0..burst_len {
            data[pos + j] = 50.0 + ((j * 13 + 7) % 100) as f64;
        }
        pos += gap;
    }
    // Add a few short spikes inside zero runs (tests spike tolerance)
    for &spike_pos in &[150, 350, 550, 750, 950] {
        if spike_pos < n {
            data[spike_pos] = 3.0;
        }
    }
    data
}

/// Generate a synthetic ActiGraph-style CSV string with the given number of rows.
fn make_csv(rows: usize) -> String {
    let mut csv = String::with_capacity(rows * 60);
    // Header (10 rows of metadata, matching default skip_rows=10)
    for i in 0..10 {
        csv.push_str(&format!("Header line {}\n", i));
    }
    // Column header
    csv.push_str("Datetime,Axis1,Axis2,Axis3,Vector Magnitude\n");
    // Data rows: 2024-01-01 00:00:00 + 60s per epoch
    let base_ts = 1704067200u64; // 2024-01-01T00:00:00 UTC
    for i in 0..rows {
        let ts = base_ts + (i as u64 * 60);
        let secs = ts % 60;
        let mins = (ts / 60) % 60;
        let hours = (ts / 3600) % 24;
        let days_total = ts / 86400;
        // Simple date calc from days since epoch (good enough for synthetic data)
        let (y, m, d) = days_to_ymd(days_total as i64);
        let axis1 = ((i * 7 + 3) % 300) as f64;
        let axis2 = ((i * 11 + 5) % 200) as f64;
        let axis3 = ((i * 13 + 7) % 150) as f64;
        let vm = (axis1 * axis1 + axis2 * axis2 + axis3 * axis3).sqrt();
        csv.push_str(&format!(
            "{:04}-{:02}-{:02} {:02}:{:02}:{:02},{:.1},{:.1},{:.1},{:.3}\n",
            y, m, d, hours, mins, secs, axis1, axis2, axis3, vm
        ));
    }
    csv
}

/// Minimal days-since-epoch to Y-M-D (for synthetic CSV generation only).
fn days_to_ymd(days: i64) -> (i64, i64, i64) {
    // Algorithm from Howard Hinnant
    let z = days + 719468;
    let era = if z >= 0 { z } else { z - 146096 } / 146097;
    let doe = z - era * 146097;
    let yoe = (doe - doe / 1460 + doe / 36524 - doe / 146096) / 365;
    let y = yoe + era * 400;
    let doy = doe - (365 * yoe + yoe / 4 - yoe / 100);
    let mp = (5 * doy + 2) / 153;
    let d = doy - (153 * mp + 2) / 5 + 1;
    let m = if mp < 10 { mp + 3 } else { mp - 9 };
    let y = if m <= 2 { y + 1 } else { y };
    (y, m, d)
}

// ---------------------------------------------------------------------------
// Benchmark groups
// ---------------------------------------------------------------------------

const SIZES: &[(usize, &str)] = &[
    (1_440, "24h"),
    (10_080, "7d"),
    (43_200, "30d"),
];

fn bench_sadeh(c: &mut Criterion) {
    let mut group = c.benchmark_group("sadeh");
    for &(size, label) in SIZES {
        let data = make_activity(size);
        group.throughput(Throughput::Elements(size as u64));
        group.bench_with_input(BenchmarkId::new("score", label), &data, |b, data| {
            b.iter(|| sadeh::score(black_box(data), black_box(-4.0)));
        });
    }
    group.finish();
}

fn bench_cole_kripke(c: &mut Criterion) {
    let mut group = c.benchmark_group("cole_kripke");
    for &(size, label) in SIZES {
        let data = make_activity(size);
        group.throughput(Throughput::Elements(size as u64));
        group.bench_with_input(BenchmarkId::new("score", label), &data, |b, data| {
            b.iter(|| cole_kripke::score(black_box(data), black_box(true)));
        });
    }
    group.finish();
}

fn bench_choi(c: &mut Criterion) {
    let mut group = c.benchmark_group("choi");
    for &(size, label) in SIZES {
        let data = make_choi_data(size);
        group.throughput(Throughput::Elements(size as u64));
        group.bench_with_input(BenchmarkId::new("detect", label), &data, |b, data| {
            b.iter(|| choi::detect(black_box(data)));
        });
    }
    group.finish();
}

const CSV_SIZES: &[(usize, &str)] = &[
    (1_000, "1k_rows"),
    (10_000, "10k_rows"),
];

fn bench_csv_parse(c: &mut Criterion) {
    let mut group = c.benchmark_group("csv_parse");
    for &(size, label) in CSV_SIZES {
        let csv_content = make_csv(size);
        group.throughput(Throughput::Elements(size as u64));
        group.bench_with_input(
            BenchmarkId::new("actigraph", label),
            &csv_content,
            |b, content| {
                b.iter(|| csv_parser::parse_actigraph_csv(black_box(content), black_box(10)));
            },
        );
    }
    group.finish();
}

criterion_group!(benches, bench_sadeh, bench_cole_kripke, bench_choi, bench_csv_parse);
criterion_main!(benches);
