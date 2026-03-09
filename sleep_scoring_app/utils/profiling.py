"""
Performance profiling utilities for the Sleep Scoring App.

Usage:
    from sleep_scoring_app.utils.profiling import profile_function, ProfileTimer

    # Decorator for automatic profiling
    @profile_function
    def expensive_operation():
        ...

    # Context manager for timing blocks
    with ProfileTimer("loading data"):
        data = load_data()

    # Get profiling report
    from sleep_scoring_app.utils.profiling import get_profile_report
    print(get_profile_report())

Enable/disable via environment variable:
    SLEEP_APP_PROFILING=1 python -m sleep_scoring_app
"""

from __future__ import annotations

import functools
import logging
import os
import time
from collections import defaultdict
from collections.abc import Callable
from contextlib import contextmanager
from dataclasses import dataclass, field
from typing import Any, TypeVar

logger = logging.getLogger(__name__)

# Check if profiling is enabled
PROFILING_ENABLED = os.environ.get("SLEEP_APP_PROFILING", "0") == "1"

# Global stats storage
_profile_stats: dict[str, list[float]] = defaultdict(list)
_call_counts: dict[str, int] = defaultdict(int)


@dataclass
class FunctionStats:
    """Statistics for a profiled function."""

    name: str
    call_count: int = 0
    total_time: float = 0.0
    min_time: float = float("inf")
    max_time: float = 0.0
    times: list[float] = field(default_factory=list)

    @property
    def avg_time(self) -> float:
        return self.total_time / self.call_count if self.call_count > 0 else 0.0

    @property
    def avg_time_ms(self) -> float:
        return self.avg_time * 1000

    @property
    def total_time_ms(self) -> float:
        return self.total_time * 1000

    @property
    def min_time_ms(self) -> float:
        return self.min_time * 1000 if self.min_time != float("inf") else 0.0

    @property
    def max_time_ms(self) -> float:
        return self.max_time * 1000


F = TypeVar("F", bound=Callable[..., Any])


def profile_function[F: Callable[..., Any]](func: F) -> F:
    """
    Decorator to profile function execution time.

    Only active when SLEEP_APP_PROFILING=1 environment variable is set.

    Example:
        @profile_function
        def expensive_operation():
            ...

    """
    if not PROFILING_ENABLED:
        return func

    @functools.wraps(func)
    def wrapper(*args, **kwargs):
        start = time.perf_counter()
        try:
            return func(*args, **kwargs)
        finally:
            elapsed = time.perf_counter() - start
            _profile_stats[func.__qualname__].append(elapsed)
            _call_counts[func.__qualname__] += 1

            # Log slow calls (> 50ms)
            if elapsed > 0.05:
                logger.warning("SLOW: %s took %.1fms", func.__qualname__, elapsed * 1000)

    return wrapper  # type: ignore


@contextmanager
def ProfileTimer(name: str):
    """
    Context manager for timing code blocks.

    Example:
        with ProfileTimer("loading file"):
            data = load_file()

    """
    if not PROFILING_ENABLED:
        yield
        return

    start = time.perf_counter()
    try:
        yield
    finally:
        elapsed = time.perf_counter() - start
        _profile_stats[f"block:{name}"].append(elapsed)
        _call_counts[f"block:{name}"] += 1

        if elapsed > 0.05:
            logger.warning("SLOW: %s took %.1fms", name, elapsed * 1000)


def get_profile_stats() -> dict[str, FunctionStats]:
    """Get profiling statistics for all tracked functions."""
    stats = {}
    for name, times in _profile_stats.items():
        stats[name] = FunctionStats(
            name=name,
            call_count=len(times),
            total_time=sum(times),
            min_time=min(times) if times else 0.0,
            max_time=max(times) if times else 0.0,
            times=times,
        )
    return stats


def get_profile_report() -> str:
    """Generate a formatted profiling report."""
    stats = get_profile_stats()

    if not stats:
        return "No profiling data collected. Set SLEEP_APP_PROFILING=1 to enable."

    lines = [
        "",
        "=" * 80,
        "PERFORMANCE PROFILE REPORT",
        "=" * 80,
        "",
        f"{'Function':<50} {'Calls':>8} {'Total':>10} {'Avg':>10} {'Max':>10}",
        "-" * 80,
    ]

    # Sort by total time descending
    sorted_stats = sorted(stats.values(), key=lambda s: s.total_time, reverse=True)

    for s in sorted_stats:
        lines.append(f"{s.name:<50} {s.call_count:>8} {s.total_time_ms:>9.1f}ms {s.avg_time_ms:>9.2f}ms {s.max_time_ms:>9.1f}ms")

    lines.extend(["", "=" * 80, ""])
    return "\n".join(lines)


def reset_profile_stats() -> None:
    """Reset all profiling statistics."""
    _profile_stats.clear()
    _call_counts.clear()


def print_profile_report() -> None:
    """Print the profiling report to stdout."""


# Convenience function to profile during drag operations
class DragProfiler:
    """
    Specialized profiler for drag operations.

    Usage:
        profiler = DragProfiler()
        profiler.start_drag()
        # ... drag operations ...
        profiler.end_drag()
        profiler.print_report()
    """

    def __init__(self) -> None:
        self.drag_start_time: float | None = None
        self.drag_stats: list[dict[str, Any]] = []
        self._drag_profile_stats: dict[str, list[float]] = defaultdict(list)

    def start_drag(self) -> None:
        """Call when drag starts."""
        self.drag_start_time = time.perf_counter()
        self._drag_profile_stats.clear()

    def record(self, operation: str, elapsed: float) -> None:
        """Record time for an operation during drag."""
        self._drag_profile_stats[operation].append(elapsed)

    def end_drag(self) -> None:
        """Call when drag ends."""
        if self.drag_start_time is None:
            return

        total_time = time.perf_counter() - self.drag_start_time
        self.drag_stats.append(
            {
                "total_time": total_time,
                "operations": dict(self._drag_profile_stats),
            }
        )
        self.drag_start_time = None

    def print_report(self) -> None:
        """Print drag profiling report."""
        if not self.drag_stats:
            return

        total_drags = len(self.drag_stats)
        avg_drag_time = sum(d["total_time"] for d in self.drag_stats) / total_drags

        # Aggregate operation stats
        all_ops: dict[str, list[float]] = defaultdict(list)
        for drag in self.drag_stats:
            for op, times in drag["operations"].items():
                all_ops[op].extend(times)

        lines = [
            "",
            "=" * 80,
            "DRAG PROFILE REPORT",
            "=" * 80,
            "",
            f"Total drags: {total_drags}",
            f"Average drag time: {avg_drag_time * 1000:.1f} ms",
            "",
            f"{'Operation':<40} {'Calls':>8} {'Total':>10} {'Avg':>10} {'Max':>10}",
            "-" * 80,
        ]

        for op, times in sorted(all_ops.items(), key=lambda x: sum(x[1]), reverse=True):
            total_time = sum(times)
            avg_time = total_time / len(times) if times else 0.0
            max_time = max(times) if times else 0.0
            lines.append(f"{op:<40} {len(times):>8} {total_time * 1000:>9.1f}ms {avg_time * 1000:>9.2f}ms {max_time * 1000:>9.1f}ms")

        lines.extend(["", "=" * 80, ""])
