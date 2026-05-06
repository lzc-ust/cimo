"""
SDL schema definitions for CIMO v1.

Provides the dataclass representation of a fully-parsed scenario file,
and the list of required / optional top-level keys.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional


@dataclass
class ScenarioMeta:
    spec_version: str
    scenario_id: str
    suite: str
    motif: str
    split: str
    seed: int


@dataclass
class WorldNodeDef:
    node_id: str
    label: str
    environment_class: str
    x: float = 0.0
    y: float = 0.0
    z: float = 0.0
    is_recharge_point: bool = False
    metadata: Dict = field(default_factory=dict)


@dataclass
class WorldEdgeDef:
    edge_id: str
    source: str
    target: str
    terrain_type: str
    distance: float
    transition_type: Optional[str] = None
    bidirectional: bool = True
    metadata: Dict = field(default_factory=dict)


@dataclass
class WorldDef:
    nodes: List[WorldNodeDef] = field(default_factory=list)
    edges: List[WorldEdgeDef] = field(default_factory=list)


@dataclass
class UnitInitDef:
    unit_id: str
    unit_type: str
    location: str
    energy: Optional[float] = None   # None = full capacity


@dataclass
class ObjectInitDef:
    object_id: str
    object_type: str
    location: Optional[str] = None
    carried_by: Optional[str] = None


@dataclass
class TargetInitDef:
    target_id: str
    target_type: str
    location: str
    metadata: Dict = field(default_factory=dict)


@dataclass
class InitialStateDef:
    units: List[UnitInitDef] = field(default_factory=list)
    objects: List[ObjectInitDef] = field(default_factory=list)
    targets: List[TargetInitDef] = field(default_factory=list)


@dataclass
class MissionDef:
    mission_id: str
    family: str
    priority: str
    release_tick: int
    deadline_tick: Optional[int]
    connectivity_requirement: str
    risk_budget: float
    assigned_units: List[str] = field(default_factory=list)
    dependencies: List[Dict] = field(default_factory=list)
    params: Dict = field(default_factory=dict)


@dataclass
class WorkloadDef:
    missions: List[MissionDef] = field(default_factory=list)


@dataclass
class DisturbanceDef:
    disturbance_id: str
    trigger_tick: int
    resolve_tick: Optional[int]
    affected_edges: List[str] = field(default_factory=list)
    affected_nodes: List[str] = field(default_factory=list)
    effect: str = "block"
    magnitude: float = 1.0


@dataclass
class BenchmarkDef:
    max_ticks: int = 10_000
    record_interval: int = 10
    reward_shaping: str = "none"
    metadata: Dict = field(default_factory=dict)


@dataclass
class ScenarioDef:
    """Fully-parsed scenario, ready for compilation into RuntimeState."""
    meta: ScenarioMeta
    imports: List[str] = field(default_factory=list)
    catalogs: Dict = field(default_factory=dict)
    world: WorldDef = field(default_factory=WorldDef)
    initial_state: InitialStateDef = field(default_factory=InitialStateDef)
    workload: WorkloadDef = field(default_factory=WorkloadDef)
    disturbances: List[DisturbanceDef] = field(default_factory=list)
    benchmark: BenchmarkDef = field(default_factory=BenchmarkDef)
    generators: Dict = field(default_factory=dict)
