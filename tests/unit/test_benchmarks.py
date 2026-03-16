"""
Benchmark tests for the heaviest backend algorithms.

Verifies each algorithm completes within 100ms on 1440 epochs (24 hours of data).
Uses time.perf_counter for portable benchmarking without requiring pytest-benchmark.
"""

from __future__ import annotations

import random
import time
from pathlib import Path

import pytest


def _generate_activity_counts(n: int, *, seed: int = 42) -> list[int]:
    """Generate realistic-looking activity counts for benchmarking."""
    rng = random.Random(seed)
    counts: list[int] = []
    for i in range(n):
        # Simulate sleep (low activity) in the middle, wake at edges
        hour = (i % 1440) / 60
        if 23 <= hour or hour < 6:
            # Sleep hours: mostly zeros with occasional movement
            counts.append(rng.choice([0, 0, 0, 0, 0, 1, 2, 5]))
        else:
            # Wake hours: higher activity
            counts.append(rng.randint(0, 500))
    return counts


def _generate_timestamps(n: int) -> list[float]:
    """Generate minute-spaced timestamps starting from a fixed epoch."""
    base = 946684800.0  # 2000-01-01 00:00:00 UTC
    return [base + i * 60.0 for i in range(n)]


N_EPOCHS = 1440  # 24 hours of 1-minute epochs
MAX_MS = 100  # Maximum allowed time in milliseconds


class TestSadehBenchmark:
    """Benchmark Sadeh 1994 algorithm on 1440 epochs."""

    def test_sadeh_completes_under_100ms(self) -> None:
        from sleep_scoring_web.services.algorithms.sadeh import SadehAlgorithm

        algo = SadehAlgorithm(variant="actilife")
        counts = _generate_activity_counts(N_EPOCHS)

        start = time.perf_counter()
        result = algo.score(counts)
        elapsed_ms = (time.perf_counter() - start) * 1000

        assert len(result) == N_EPOCHS
        assert all(v in (0, 1) for v in result), "Scores must be 0 or 1"
        assert elapsed_ms < MAX_MS, (
            f"Sadeh took {elapsed_ms:.1f}ms, expected < {MAX_MS}ms"
        )


class TestColeKripkeBenchmark:
    """Benchmark Cole-Kripke 1992 algorithm on 1440 epochs."""

    def test_cole_kripke_completes_under_100ms(self) -> None:
        from sleep_scoring_web.services.algorithms.cole_kripke import ColeKripkeAlgorithm

        algo = ColeKripkeAlgorithm(variant="actilife")
        counts = _generate_activity_counts(N_EPOCHS)

        start = time.perf_counter()
        result = algo.score(counts)
        elapsed_ms = (time.perf_counter() - start) * 1000

        assert len(result) == N_EPOCHS
        assert all(v in (0, 1) for v in result), "Scores must be 0 or 1"
        assert elapsed_ms < MAX_MS, (
            f"Cole-Kripke took {elapsed_ms:.1f}ms, expected < {MAX_MS}ms"
        )


class TestChoiBenchmark:
    """Benchmark Choi 2011 nonwear detection on 1440 epochs."""

    def test_choi_detect_mask_completes_under_100ms(self) -> None:
        from sleep_scoring_web.services.algorithms.choi import ChoiAlgorithm

        algo = ChoiAlgorithm()
        counts = _generate_activity_counts(N_EPOCHS)

        start = time.perf_counter()
        result = algo.detect_mask(counts)
        elapsed_ms = (time.perf_counter() - start) * 1000

        assert len(result) == N_EPOCHS
        assert all(v in (0, 1) for v in result), "Mask must be 0 or 1"
        assert elapsed_ms < MAX_MS, (
            f"Choi took {elapsed_ms:.1f}ms, expected < {MAX_MS}ms"
        )


class TestComplexityBenchmark:
    """Benchmark complexity scoring on 1440 epochs."""

    def test_complexity_completes_under_100ms(self) -> None:
        from sleep_scoring_web.services.algorithms.sadeh import SadehAlgorithm
        from sleep_scoring_web.services.complexity import compute_pre_complexity

        counts = _generate_activity_counts(N_EPOCHS)
        timestamps = _generate_timestamps(N_EPOCHS)

        # Pre-compute sleep scores (not part of the benchmark)
        algo = SadehAlgorithm(variant="actilife")
        sleep_scores = algo.score(counts)

        # Generate Choi nonwear mask (not part of the benchmark)
        from sleep_scoring_web.services.algorithms.choi import ChoiAlgorithm

        choi = ChoiAlgorithm()
        choi_nonwear = choi.detect_mask(counts)

        activity_floats = [float(c) for c in counts]

        start = time.perf_counter()
        score, features = compute_pre_complexity(
            timestamps=timestamps,
            activity_counts=activity_floats,
            sleep_scores=sleep_scores,
            choi_nonwear=choi_nonwear,
            diary_onset_time="22:30",
            diary_wake_time="7:00",
            diary_nap_count=0,
            analysis_date="2000-01-01",
        )
        elapsed_ms = (time.perf_counter() - start) * 1000

        assert isinstance(score, int)
        assert isinstance(features, dict)
        assert elapsed_ms < MAX_MS, (
            f"Complexity took {elapsed_ms:.1f}ms, expected < {MAX_MS}ms"
        )


class TestCSVParsingBenchmark:
    """Benchmark CSV parsing and column detection on a 1000-row synthetic file."""

    def test_csv_parsing_completes_under_200ms(self, tmp_path: Path) -> None:
        import pandas as pd
        from sleep_scoring_web.services.loaders.csv_loader import CSVLoaderService

        # Generate a realistic 1000-row ActiGraph-style CSV file
        rng = random.Random(42)
        rows = 1000
        csv_path = tmp_path / "test_data.csv"
        with open(csv_path, "w") as f:
            f.write("Date,Time,Axis1,Axis2,Axis3,Steps,Lux,Inclinometer Off,Inclinometer Standing,Inclinometer Sitting,Inclinometer Lying,Vector Magnitude\n")
            base_ts = 946684800  # 2000-01-01 00:00:00 UTC
            for i in range(rows):
                ts = base_ts + i * 60
                dt = time.strftime("%m/%d/%Y", time.gmtime(ts))
                tm = time.strftime("%H:%M:%S", time.gmtime(ts))
                a1 = rng.randint(0, 500)
                a2 = rng.randint(0, 300)
                a3 = rng.randint(0, 300)
                vm = (a1**2 + a2**2 + a3**2) ** 0.5
                f.write(f"{dt},{tm},{a1},{a2},{a3},{rng.randint(0,20)},{rng.randint(0,200)},0,1,0,0,{vm:.2f}\n")

        loader = CSVLoaderService(skip_rows=0)

        start = time.perf_counter()
        result = loader.load_file(str(csv_path))
        elapsed_ms = (time.perf_counter() - start) * 1000

        assert "activity_data" in result
        assert len(result["activity_data"]) == rows
        assert elapsed_ms < 200, (
            f"CSV parsing took {elapsed_ms:.1f}ms, expected < 200ms"
        )


class TestMarkerPlacementBenchmark:
    """Benchmark marker placement on a full day of data."""

    def test_marker_placement_completes_under_500ms(self) -> None:
        from sleep_scoring_web.services.algorithms.sadeh import SadehAlgorithm
        from sleep_scoring_web.services.algorithms.choi import ChoiAlgorithm
        from sleep_scoring_web.services.marker_placement import run_auto_scoring

        counts = _generate_activity_counts(N_EPOCHS)
        timestamps = _generate_timestamps(N_EPOCHS)

        # Pre-compute algorithm outputs (not part of the benchmark)
        algo = SadehAlgorithm(variant="actilife")
        sleep_scores = algo.score(counts)
        choi = ChoiAlgorithm()
        choi_nonwear = choi.detect_mask(counts)

        start = time.perf_counter()
        result = run_auto_scoring(
            timestamps=timestamps,
            activity_counts=[float(c) for c in counts],
            sleep_scores=sleep_scores,
            choi_nonwear=choi_nonwear,
            diary_bed_time="22:30",
            diary_onset_time="23:00",
            diary_wake_time="7:00",
            diary_naps=[("13:00", "14:00")],
            diary_nonwear=[("08:00", "09:00")],
            analysis_date="2000-01-01",
        )
        elapsed_ms = (time.perf_counter() - start) * 1000

        assert isinstance(result, dict)
        assert "sleep_markers" in result
        assert elapsed_ms < 500, (
            f"Marker placement took {elapsed_ms:.1f}ms, expected < 500ms"
        )


class TestExportGenerationBenchmark:
    """Benchmark CSV export generation from pre-built row data."""

    def test_export_generation_completes_under_1s(self) -> None:
        from sleep_scoring_web.services.export_service import (
            ExportService,
            DEFAULT_COLUMNS,
        )

        # Build 10 files x ~30 dates x 1 marker = 300 rows of realistic data
        rng = random.Random(42)
        rows: list[dict[str, str]] = []
        for file_id in range(1, 11):
            for day in range(30):
                rows.append({
                    "Filename": f"participant_{file_id:03d}.csv",
                    "File ID": str(file_id),
                    "Participant ID": f"P{file_id:03d}",
                    "Study Date": f"2024-01-{day + 1:02d}",
                    "Period Index": "1",
                    "Marker Type": "Main Sleep",
                    "Onset Time": "23:15",
                    "Offset Time": "07:30",
                    "Onset Datetime": "2024-01-01 23:15:00",
                    "Offset Datetime": "2024-01-02 07:30:00",
                    "Time in Bed (min)": "495",
                    "Total Sleep Time (min)": str(rng.randint(350, 480)),
                    "WASO (min)": str(rng.randint(5, 60)),
                    "Sleep Onset Latency (min)": str(rng.randint(2, 30)),
                    "Number of Awakenings": str(rng.randint(1, 15)),
                    "Avg Awakening Length (min)": f"{rng.uniform(1, 10):.2f}",
                    "Sleep Efficiency (%)": f"{rng.uniform(75, 99):.2f}",
                    "Movement Index": f"{rng.uniform(5, 40):.2f}",
                    "Fragmentation Index": f"{rng.uniform(5, 40):.2f}",
                    "Sleep Fragmentation Index": f"{rng.uniform(10, 60):.2f}",
                    "Total Activity Counts": str(rng.randint(500, 5000)),
                    "Non-zero Epochs": str(rng.randint(50, 200)),
                    "Algorithm": "Sadeh 1994 (ActiLife)",
                    "Detection Rule": "3 Epochs / 5 Min",
                    "Verification Status": "Verified",
                    "Scored By": "testuser",
                    "Is No Sleep": "False",
                    "Needs Consensus": "False",
                    "Notes": "",
                })

        # Use the static _generate_csv method via a mock-free approach
        # ExportService._generate_csv is a bound method, so we need an instance
        # but _generate_csv doesn't use self.db, so we can pass None
        service = ExportService(db=None)  # type: ignore[arg-type]

        start = time.perf_counter()
        csv_output = service._generate_csv(rows, DEFAULT_COLUMNS, include_header=True)
        elapsed_ms = (time.perf_counter() - start) * 1000

        assert len(csv_output) > 0
        assert csv_output.count("\n") >= 300  # At least 300 data rows + header
        assert elapsed_ms < 1000, (
            f"Export generation took {elapsed_ms:.1f}ms, expected < 1000ms"
        )


class TestComplexityScoringBenchmark:
    """Benchmark complexity scoring specifically for a realistic night."""

    def test_complexity_night_window_under_100ms(self) -> None:
        from sleep_scoring_web.services.algorithms.sadeh import SadehAlgorithm
        from sleep_scoring_web.services.algorithms.choi import ChoiAlgorithm
        from sleep_scoring_web.services.complexity import compute_pre_complexity

        # Generate a realistic night: 8 hours of mostly-sleep data
        # (more realistic than the full 24h which includes lots of wake)
        rng = random.Random(99)
        night_epochs = 480  # 8 hours
        counts: list[int] = []
        for i in range(night_epochs):
            # Mostly sleep with occasional brief awakenings
            if rng.random() < 0.85:
                counts.append(rng.choice([0, 0, 0, 1, 2]))
            else:
                counts.append(rng.randint(10, 200))

        timestamps = [946713600.0 + i * 60.0 for i in range(night_epochs)]  # Start at 23:00

        algo = SadehAlgorithm(variant="actilife")
        sleep_scores = algo.score(counts)
        choi = ChoiAlgorithm()
        choi_nonwear = choi.detect_mask(counts)

        start = time.perf_counter()
        score, features = compute_pre_complexity(
            timestamps=timestamps,
            activity_counts=[float(c) for c in counts],
            sleep_scores=sleep_scores,
            choi_nonwear=choi_nonwear,
            diary_onset_time="23:00",
            diary_wake_time="7:00",
            diary_nap_count=0,
            analysis_date="2000-01-01",
        )
        elapsed_ms = (time.perf_counter() - start) * 1000

        assert isinstance(score, int)
        assert isinstance(features, dict)
        assert score >= 0, "Complexity score should be non-negative"
        assert elapsed_ms < MAX_MS, (
            f"Night complexity scoring took {elapsed_ms:.1f}ms, expected < {MAX_MS}ms"
        )
