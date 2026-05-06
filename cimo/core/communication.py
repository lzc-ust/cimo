"""
Communication system for CIMO v1.

Determines:
- Whether two units are within direct communication range.
- Whether relay connectivity is established via mobile_relay units.
- Network connectivity fraction for coverage metrics.
"""

from __future__ import annotations

import math
from typing import Dict, List, Optional, Set, Tuple

from cimo.core.ids import NodeId, UnitId


def _node_distance(
    node_positions: Dict[NodeId, Tuple[float, float, float]],
    a: NodeId,
    b: NodeId,
) -> float:
    """Euclidean distance between two node positions."""
    xa, ya, za = node_positions.get(a, (0.0, 0.0, 0.0))
    xb, yb, zb = node_positions.get(b, (0.0, 0.0, 0.0))
    return math.sqrt((xa - xb) ** 2 + (ya - yb) ** 2 + (za - zb) ** 2)


def check_direct_link(
    loc_a: NodeId,
    loc_b: NodeId,
    comm_range_a: float,
    comm_range_b: float,
    node_positions: Dict[NodeId, Tuple[float, float, float]],
    comm_factor: float = 1.0,
) -> bool:
    """
    Return True if units at loc_a and loc_b can communicate directly.

    The effective range is min(range_a, range_b) * comm_factor.
    """
    dist = _node_distance(node_positions, loc_a, loc_b)
    effective_range = min(comm_range_a, comm_range_b) * comm_factor
    return dist <= effective_range


def build_comm_graph(
    unit_locations: Dict[UnitId, NodeId],
    unit_comm_ranges: Dict[UnitId, float],
    unit_relay_capable: Dict[UnitId, bool],
    unit_relay_bonus: Dict[UnitId, float],
    node_positions: Dict[NodeId, Tuple[float, float, float]],
    terrain_comm_factors: Dict[NodeId, float],
) -> Dict[UnitId, Set[UnitId]]:
    """
    Build the communication adjacency graph for all active units.

    Returns a dict mapping each unit_id to the set of units it can
    directly communicate with (excluding itself).
    """
    adj: Dict[UnitId, Set[UnitId]] = {uid: set() for uid in unit_locations}
    unit_ids = list(unit_locations.keys())

    for i, uid_a in enumerate(unit_ids):
        for uid_b in unit_ids[i + 1:]:
            loc_a = unit_locations[uid_a]
            loc_b = unit_locations[uid_b]
            range_a = unit_comm_ranges.get(uid_a, 0.0)
            range_b = unit_comm_ranges.get(uid_b, 0.0)
            # Apply terrain comm factor (use the worse of the two endpoints)
            factor_a = terrain_comm_factors.get(loc_a, 1.0)
            factor_b = terrain_comm_factors.get(loc_b, 1.0)
            comm_factor = min(factor_a, factor_b)
            # Relay bonus: if either unit is a relay, boost range
            relay_bonus = 0.0
            if unit_relay_capable.get(uid_a):
                relay_bonus = max(relay_bonus, unit_relay_bonus.get(uid_a, 0.0))
            if unit_relay_capable.get(uid_b):
                relay_bonus = max(relay_bonus, unit_relay_bonus.get(uid_b, 0.0))
            effective_range_a = (range_a + relay_bonus) * comm_factor
            effective_range_b = (range_b + relay_bonus) * comm_factor
            dist = _node_distance(node_positions, loc_a, loc_b)
            if dist <= max(effective_range_a, effective_range_b):
                adj[uid_a].add(uid_b)
                adj[uid_b].add(uid_a)

    return adj


def is_connected(
    adj: Dict[UnitId, Set[UnitId]],
    unit_ids: List[UnitId],
) -> bool:
    """Return True if all given units form a single connected component."""
    if not unit_ids:
        return True
    visited: Set[UnitId] = set()
    stack = [unit_ids[0]]
    while stack:
        u = stack.pop()
        if u in visited:
            continue
        visited.add(u)
        for v in adj.get(u, set()):
            if v in unit_ids and v not in visited:
                stack.append(v)
    return all(u in visited for u in unit_ids)


def connectivity_fraction(
    adj: Dict[UnitId, Set[UnitId]],
    unit_ids: List[UnitId],
) -> float:
    """
    Return fraction of unit pairs that are in the same connected component.
    """
    if len(unit_ids) <= 1:
        return 1.0
    in_same = 0
    total_pairs = 0
    for i, a in enumerate(unit_ids):
        for b in unit_ids[i + 1:]:
            total_pairs += 1
            # BFS from a to b
            visited: Set[UnitId] = set()
            queue = [a]
            found = False
            while queue:
                u = queue.pop()
                if u == b:
                    found = True
                    break
                if u in visited:
                    continue
                visited.add(u)
                for v in adj.get(u, set()):
                    if v in unit_ids:
                        queue.append(v)
            if found:
                in_same += 1
    return in_same / total_pairs if total_pairs > 0 else 1.0
