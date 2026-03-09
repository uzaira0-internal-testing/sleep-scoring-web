"""Demo data test fixtures."""

from __future__ import annotations

from pathlib import Path

import pytest

# Demo data directory relative to project root
DEMO_DATA_DIR = Path(__file__).parent.parent.parent / "demo_data"


@pytest.fixture
def demo_data_dir() -> Path:
    """Return path to demo_data directory."""
    assert DEMO_DATA_DIR.exists(), f"Demo data directory not found: {DEMO_DATA_DIR}"
    return DEMO_DATA_DIR


@pytest.fixture
def activity_dir(demo_data_dir: Path) -> Path:
    """Return path to activity data directory."""
    path = demo_data_dir / "activity"
    assert path.exists(), f"Activity directory not found: {path}"
    return path


@pytest.fixture
def diary_dir(demo_data_dir: Path) -> Path:
    """Return path to diary data directory."""
    path = demo_data_dir / "diary"
    assert path.exists(), f"Diary directory not found: {path}"
    return path


@pytest.fixture
def nonwear_dir(demo_data_dir: Path) -> Path:
    """Return path to nonwear data directory."""
    path = demo_data_dir / "nonwear"
    assert path.exists(), f"Nonwear directory not found: {path}"
    return path


# Device format info for parameterized tests
DEVICE_FORMATS = [
    pytest.param("actigraph", 10, ["Date", "Time", "Axis1"], id="actigraph"),
    pytest.param("actiwatch", 7, ["Date", "Time", "Activity"], id="actiwatch"),
    pytest.param("axivity", 6, ["timestamp", "x", "y", "z"], id="axivity"),
    pytest.param("geneactiv", 7, ["timestamp", "x", "y", "z"], id="geneactiv"),
    pytest.param("generic", 0, ["datetime", "activity_count"], id="generic"),
    pytest.param("motionwatch", 4, ["Date/Time", "Activity"], id="motionwatch"),
]


@pytest.fixture(params=DEVICE_FORMATS)
def device_format(request):
    """Parameterized fixture for device formats."""
    return {
        "name": request.param[0],
        "skip_rows": request.param[1],
        "expected_columns": request.param[2],
    }
