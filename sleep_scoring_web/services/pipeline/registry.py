"""
Component registry for pipeline discovery and instantiation.

Each implementation registers itself at import time via @register.
The API can query available components per role for discovery endpoints.
"""

from __future__ import annotations

from enum import StrEnum
from typing import Any


class PipelineRole(StrEnum):
    """Valid pipeline component roles."""

    EPOCH_CLASSIFIER = "epoch_classifier"
    BOUT_DETECTOR = "bout_detector"
    PERIOD_GUIDER = "period_guider"
    PERIOD_CONSTRUCTOR = "period_constructor"
    NONWEAR_DETECTOR = "nonwear_detector"
    DIARY_PREPROCESSOR = "diary_preprocessor"


_REGISTRY: dict[PipelineRole, dict[str, type]] = {role: {} for role in PipelineRole}
_INSTANCE_CACHE: dict[tuple[PipelineRole, str], Any] = {}


def register(role: str | PipelineRole, component_id: str) -> Any:
    """Class decorator that registers a component under a role."""
    role_enum = PipelineRole(role)

    def decorator(cls: type) -> type:
        _REGISTRY[role_enum][component_id] = cls
        _INSTANCE_CACHE.pop((role_enum, component_id), None)
        return cls

    return decorator


def get_component(role: str | PipelineRole, component_id: str) -> Any:
    """Return a cached singleton for a registered component."""
    role_enum = PipelineRole(role)
    cache_key = (role_enum, component_id)
    cached = _INSTANCE_CACHE.get(cache_key)
    if cached is not None:
        return cached
    registry = _REGISTRY[role_enum]
    if component_id not in registry:
        msg = f"Unknown {role_enum}: {component_id!r}. Available: {sorted(registry)}"
        raise ValueError(msg)
    instance = registry[component_id]()
    _INSTANCE_CACHE[cache_key] = instance
    return instance


def describe_pipeline() -> dict[str, list[str]]:
    """Return available component IDs per role, for API discovery."""
    return {role.value: sorted(components) for role, components in _REGISTRY.items()}
