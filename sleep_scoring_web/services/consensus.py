"""Consensus helper utilities shared by API endpoints."""

from __future__ import annotations

import hashlib
import json
from typing import Any


def _normalize_marker(marker: dict[str, Any]) -> dict[str, Any]:
    """Normalize marker payload for stable hashing."""
    out: dict[str, Any] = {}
    for key, value in marker.items():
        if isinstance(value, float):
            # Keep stable precision while preserving second-level semantics.
            out[key] = round(value, 6)
        else:
            out[key] = value
    return out


def canonicalize_candidate_payload(
    sleep_markers: list[dict[str, Any]] | None,
    nonwear_markers: list[dict[str, Any]] | None,
    is_no_sleep: bool,
) -> dict[str, Any]:
    """Return a canonical dict used for candidate identity/hash."""
    sleep = [_normalize_marker(m) for m in (sleep_markers or [])]
    nonwear = [_normalize_marker(m) for m in (nonwear_markers or [])]

    sleep.sort(
        key=lambda m: (
            m.get("marker_index") if m.get("marker_index") is not None else 10**9,
            m.get("onset_timestamp", 0),
            m.get("offset_timestamp", 0),
            m.get("marker_type", ""),
        )
    )
    nonwear.sort(
        key=lambda m: (
            m.get("marker_index") if m.get("marker_index") is not None else 10**9,
            m.get("start_timestamp", 0),
            m.get("end_timestamp", 0),
        )
    )

    # Candidate identity is based on sleep markers + no-sleep flag only.
    # Nonwear differences should not create separate candidate sets.
    return {
        "sleep_markers": sleep,
        "is_no_sleep": bool(is_no_sleep),
    }


def compute_candidate_hash(
    sleep_markers: list[dict[str, Any]] | None,
    nonwear_markers: list[dict[str, Any]] | None,
    is_no_sleep: bool,
) -> str:
    """Compute SHA-256 hash for marker set identity."""
    payload = canonicalize_candidate_payload(sleep_markers, nonwear_markers, is_no_sleep)
    blob = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()

