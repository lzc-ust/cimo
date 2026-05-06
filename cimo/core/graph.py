"""
Metric graph for CIMO v1.
The world is modelled as a typed weighted directed graph:
  - Nodes represent discrete locations.
  - Edges represent traversable segments with terrain type and distance.
"""

from __future__ import annotations

import math
from typing import Dict, List, Optional, Set, Tuple

from cimo.core.datatypes import GraphEdge, GraphNode, TerrainSpec, JointAccessRule
from cimo.core.enums import MobilityClass, TeamMode, TerrainType
from cimo.core.ids import EdgeId, NodeId


class MetricGraph:
    """
    Typed metric graph.

    Supports:
    - Adding nodes and directed edges.
    - Querying neighbour nodes and edges.
    - Checking solo and joint access for a given mobility class / team mode.
    - Computing shortest path (Dijkstra) between nodes with access constraints.
    """

    def __init__(self) -> None:
        self._nodes: Dict[NodeId, GraphNode] = {}
        self._edges: Dict[EdgeId, GraphEdge] = {}
        # Adjacency: node -> list of outgoing edges
        self._adj: Dict[NodeId, List[EdgeId]] = {}
        # Terrain specs (injected from catalog)
        self._terrain_specs: Dict[str, TerrainSpec] = {}

    # ------------------------------------------------------------------
    # Build
    # ------------------------------------------------------------------

    def add_node(self, node: GraphNode) -> None:
        self._nodes[node.node_id] = node
        if node.node_id not in self._adj:
            self._adj[node.node_id] = []

    def add_edge(self, edge: GraphEdge) -> None:
        self._edges[edge.edge_id] = edge
        if edge.source not in self._adj:
            self._adj[edge.source] = []
        self._adj[edge.source].append(edge.edge_id)

    def set_terrain_specs(self, specs: Dict[str, TerrainSpec]) -> None:
        self._terrain_specs = specs

    # ------------------------------------------------------------------
    # Query
    # ------------------------------------------------------------------

    def get_node(self, node_id: NodeId) -> Optional[GraphNode]:
        return self._nodes.get(node_id)

    def get_edge(self, edge_id: EdgeId) -> Optional[GraphEdge]:
        return self._edges.get(edge_id)

    def nodes(self) -> List[GraphNode]:
        return list(self._nodes.values())

    def edges(self) -> List[GraphEdge]:
        return list(self._edges.values())

    def outgoing_edges(self, node_id: NodeId) -> List[GraphEdge]:
        return [self._edges[eid] for eid in self._adj.get(node_id, [])]

    def edge_between(self, source: NodeId, target: NodeId) -> Optional[GraphEdge]:
        for eid in self._adj.get(source, []):
            e = self._edges[eid]
            if e.target == target:
                return e
        return None

    # ------------------------------------------------------------------
    # Access checks
    # ------------------------------------------------------------------

    def can_solo_traverse(
        self,
        edge: GraphEdge,
        mobility_class: MobilityClass,
    ) -> bool:
        """Return True if the mobility class can traverse this edge alone."""
        if not edge.is_operable:
            return False
        spec = self._terrain_specs.get(edge.terrain_type.value)
        if spec is None:
            return False
        access = spec.solo_access.get(mobility_class.value, "deny")
        return access == "pass"

    def can_joint_traverse(
        self,
        edge: GraphEdge,
        actor_class: MobilityClass,
        passenger_class: MobilityClass,
        mode: TeamMode,
    ) -> bool:
        """Return True if actor+passenger in given mode can traverse this edge."""
        if not edge.is_operable:
            return False
        spec = self._terrain_specs.get(edge.terrain_type.value)
        if spec is None:
            return False
        for rule in spec.joint_access:
            if (
                rule.mode == mode.value
                and rule.actor_class == actor_class.value
                and rule.passenger_class == passenger_class.value
            ):
                return rule.passable
        return False

    # ------------------------------------------------------------------
    # Shortest path (Dijkstra by distance)
    # ------------------------------------------------------------------

    def shortest_path(
        self,
        source: NodeId,
        target: NodeId,
        mobility_class: MobilityClass,
        team_mode: Optional[TeamMode] = None,
        partner_class: Optional[MobilityClass] = None,
    ) -> Optional[Tuple[List[NodeId], float]]:
        """
        Find shortest traversable path from source to target.

        Returns (node_list, total_distance) or None if unreachable.
        """
        import heapq

        dist: Dict[NodeId, float] = {source: 0.0}
        prev: Dict[NodeId, Optional[NodeId]] = {source: None}
        heap: List[Tuple[float, NodeId]] = [(0.0, source)]

        while heap:
            d, u = heapq.heappop(heap)
            if d > dist.get(u, math.inf):
                continue
            if u == target:
                break
            for edge in self.outgoing_edges(u):
                # Check access
                if team_mode and team_mode != TeamMode.independent and partner_class:
                    ok = self.can_joint_traverse(edge, mobility_class, partner_class, team_mode)
                else:
                    ok = self.can_solo_traverse(edge, mobility_class)
                if not ok:
                    continue
                nd = d + edge.distance
                if nd < dist.get(edge.target, math.inf):
                    dist[edge.target] = nd
                    prev[edge.target] = u
                    heapq.heappush(heap, (nd, edge.target))

        if target not in dist:
            return None

        # Reconstruct path
        path: List[NodeId] = []
        cur: Optional[NodeId] = target
        while cur is not None:
            path.append(cur)
            cur = prev.get(cur)
        path.reverse()
        return path, dist[target]

    def euclidean_distance(self, a: NodeId, b: NodeId) -> float:
        """Straight-line Euclidean distance between two nodes."""
        na = self._nodes.get(a)
        nb = self._nodes.get(b)
        if na is None or nb is None:
            return math.inf
        return math.sqrt((na.x - nb.x) ** 2 + (na.y - nb.y) ** 2 + (na.z - nb.z) ** 2)

    def set_edge_operable(self, edge_id: EdgeId, operable: bool) -> None:
        """Toggle an edge's operability (used by disturbance system)."""
        if edge_id in self._edges:
            self._edges[edge_id].is_operable = operable
