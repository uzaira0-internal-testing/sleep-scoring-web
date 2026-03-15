"""
Benchmark tests for the heaviest backend algorithms.

Verifies each algorithm completes within 100ms on 1440 epochs (24 hours of data).
Uses time.perf_counter for portable benchmarking without requiring pytest-benchmark.
"""

from __future__ import annotations

import random
import time

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
