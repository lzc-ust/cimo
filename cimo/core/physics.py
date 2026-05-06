"""
Physics calculations for CIMO v1.

Computes:
- Travel time (ticks) for a unit to traverse an edge given team mode.
- Energy consumed during traversal.
- Idle energy cost per tick.
- Action energy cost.
- Risk accumulation during traversal.
"""

from __future__ import annotations

import math
from typing import Optional

from cimo.core.datatypes import GraphEdge, TeamModeSpec, UnitTypeSpec
from cimo.core.enums import MobilityClass, TeamMode, TerrainType
from cimo.core.ids import UnitId


def traverse_time_ticks(
    unit_spec: UnitTypeSpec,
    edge: GraphEdge,
    team_mode_spec: Optional[TeamModeSpec] = None,
) -> int:
    """
    Compute integer ticks required for a unit to traverse an edge.

    Formula:
        base_speed = unit_spec.speed_by_terrain[terrain]
        effective_speed = base_speed * team_mode_speed_multiplier
        time = ceil(distance / effective_speed)

    Returns at least 1 tick.
    """
    terrain_key = edge.terrain_type.value
    base_speed = unit_spec.speed_by_terrain.get(terrain_key, 0.0)
    if base_speed <= 0:
        # Unit cannot traverse this terrain (should be caught by access check first)
        return int(1e9)

    speed_mult = 1.0
    if team_mode_spec is not None:
        speed_mult = team_mode_spec.speed_multiplier

    effective_speed = base_speed * speed_mult
    ticks = math.ceil(edge.distance / effective_speed)
    return max(1, ticks)


def traverse_energy_cost(
    unit_spec: UnitTypeSpec,
    edge: GraphEdge,
    team_mode_spec: Optional[TeamModeSpec] = None,
) -> float:
    """
    Compute energy consumed to traverse an edge.

    Formula:
        base_cost_per_distance = unit_spec.energy.move_cost_per_distance[terrain]
        energy = base_cost_per_distance * distance * energy_multiplier
    """
    terrain_key = edge.terrain_type.value
    cost_per_dist = unit_spec.energy.move_cost_per_distance.get(terrain_key, 0.0)
    energy_mult = 1.0
    if team_mode_spec is not None:
        energy_mult = team_mode_spec.energy_multiplier
    return cost_per_dist * edge.distance * energy_mult


def idle_energy_cost(unit_spec: UnitTypeSpec, ticks: int = 1) -> float:
    """Energy consumed while idle for `ticks` ticks."""
    return unit_spec.energy.idle_cost_per_tick * ticks


def action_energy_cost(unit_spec: UnitTypeSpec, action_type: str) -> float:
    """Energy consumed for a single atomic action (inspect, pick, etc.)."""
    return unit_spec.energy.action_costs.get(action_type, 0.0)


def risk_during_traverse(
    unit_spec: UnitTypeSpec,
    edge: GraphEdge,
    terrain_spec_risk_rate: float,
    ticks: int,
) -> float:
    """
    Compute risk accumulated during traversal.

    risk = terrain_risk_rate * distance * unit_mass_factor
    (unit mass factor = unit mass / 10.0 as a simple normalisation)
    """
    mass_factor = unit_spec.mass / 10.0
    return terrain_spec_risk_rate * edge.distance * mass_factor


def compute_recharge_ticks(unit_spec: UnitTypeSpec, deficit: float) -> int:
    """
    Ticks needed to recharge `deficit` energy units.
    Returns 0 if deficit <= 0.
    """
    if deficit <= 0:
        return 0
    rate = unit_spec.energy.recharge_rate
    if rate <= 0:
        return int(1e9)
    return math.ceil(deficit / rate)


def recharge_amount(unit_spec: UnitTypeSpec, ticks: int) -> float:
    """Energy recharged in `ticks` ticks."""
    return unit_spec.energy.recharge_rate * ticks


def clamp_energy(current: float, delta: float, capacity: float) -> float:
    """Apply an energy delta, clamping to [0, capacity]."""
    return max(0.0, min(capacity, current + delta))
