"""
Sensing system for CIMO v1.

Computes:
- Whether a unit can sense a target given range and terrain visibility.
- Assessment quality for inspect/verify/diagnose.
- Duration in ticks for assessment actions.
"""

from __future__ import annotations

import math
from typing import Dict, Optional, Tuple

from cimo.core.datatypes import SensingSpec
from cimo.core.enums import AssessmentMode
from cimo.core.ids import NodeId, TargetId, UnitId


def _node_distance_2d(
    node_positions: Dict[NodeId, Tuple[float, float, float]],
    a: NodeId,
    b: NodeId,
) -> float:
    xa, ya, _ = node_positions.get(a, (0.0, 0.0, 0.0))
    xb, yb, _ = node_positions.get(b, (0.0, 0.0, 0.0))
    return math.sqrt((xa - xb) ** 2 + (ya - yb) ** 2)


def can_sense_target(
    unit_location: NodeId,
    target_location: NodeId,
    sensing_spec: SensingSpec,
    node_positions: Dict[NodeId, Tuple[float, float, float]],
    terrain_visibility_factor: float = 1.0,
) -> bool:
    """
    Return True if a unit at unit_location can sense the target.

    Effective sensing range = sensing_spec.range * terrain_visibility_factor.
    """
    dist = _node_distance_2d(node_positions, unit_location, target_location)
    effective_range = sensing_spec.range * terrain_visibility_factor
    return dist <= effective_range


def assessment_duration(
    sensing_spec: SensingSpec,
    mode: AssessmentMode,
) -> int:
    """Return the ticks required for an assessment action."""
    return sensing_spec.durations.get(mode.value, 5)


def assessment_quality(
    sensing_spec: SensingSpec,
    distance: float,
    terrain_visibility_factor: float = 1.0,
) -> float:
    """
    Compute assessment quality [0, 1].

    Quality degrades linearly with distance relative to effective range.
    """
    effective_range = sensing_spec.range * terrain_visibility_factor
    if effective_range <= 0:
        return 0.0
    dist_fraction = min(1.0, distance / effective_range)
    return sensing_spec.base_quality * (1.0 - dist_fraction)


def compute_sensing_coverage(
    unit_locations: Dict[UnitId, NodeId],
    unit_sensing_ranges: Dict[UnitId, float],
    target_locations: Dict[TargetId, NodeId],
    node_positions: Dict[NodeId, Tuple[float, float, float]],
    terrain_visibility_factors: Dict[NodeId, float],
) -> Dict[TargetId, bool]:
    """
    For each target, determine whether at least one unit can sense it.

    Returns a dict mapping target_id -> bool (covered or not).
    """
    covered: Dict[TargetId, bool] = {}
    for tid, t_loc in target_locations.items():
        covered[tid] = False
        for uid, u_loc in unit_locations.items():
            vis = terrain_visibility_factors.get(u_loc, 1.0)
            s_range = unit_sensing_ranges.get(uid, 0.0) * vis
            dist = _node_distance_2d(node_positions, u_loc, t_loc)
            if dist <= s_range:
                covered[tid] = True
                break
    return covered
