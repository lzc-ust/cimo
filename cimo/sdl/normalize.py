"""
Scenario normalization for CIMO-SDL.

Applies default values and canonicalises field names before compilation.
"""

from __future__ import annotations

from typing import Dict


def normalize_scenario_dict(raw: Dict) -> Dict:
    """
    Apply defaults and normalise a raw scenario dict in-place.

    Called before compilation to ensure consistent data shapes.
    """
    # Ensure all top-level keys exist (even if empty)
    for key in ("meta", "imports", "catalogs", "world", "initial_state",
                "workload", "disturbances", "benchmark", "generators"):
        raw.setdefault(key, {} if key not in ("imports", "disturbances") else [])

    # Normalize world
    world = raw["world"]
    if isinstance(world, dict):
        world.setdefault("nodes", [])
        world.setdefault("edges", [])

    # Normalize initial_state
    init = raw["initial_state"]
    if isinstance(init, dict):
        init.setdefault("units", [])
        init.setdefault("objects", [])
        init.setdefault("targets", [])

    # Normalize workload
    wl = raw["workload"]
    if isinstance(wl, dict):
        wl.setdefault("missions", [])

    # Normalize benchmark
    bm = raw["benchmark"]
    if isinstance(bm, dict):
        bm.setdefault("max_ticks", 10_000)
        bm.setdefault("record_interval", 10)
        bm.setdefault("reward_shaping", "none")

    return raw
