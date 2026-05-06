"""
Core data types for CIMO v1.
All dataclasses use frozen=True where appropriate to enforce immutability
of catalog / spec entries. Runtime mutable state lives in state.py.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional, Set

from cimo.core.enums import (
    EnvironmentClass,
    MobilityClass,
    SizeClass,
    TeamMode,
    TerrainType,
    TransitionType,
    UnitTypeId,
    ObjectTypeId,
    Priority,
    ConnectivityRequirement,
    MissionDependencyType,
    MissionFamily,
    AssessmentMode,
    CoverageMode,
    ActionType,
)
from cimo.core.ids import (
    NodeId, EdgeId, UnitId, ObjectId, TargetId, MissionId,
    DisturbanceId, ActionId, Tick,
)


# ---------------------------------------------------------------------------
# Catalog / spec data types (immutable after loading)
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class JointAccessRule:
    """One joint-access rule inside a terrain definition."""
    mode: str            # TeamMode value
    actor_class: str     # MobilityClass value
    passenger_class: str # MobilityClass value
    passable: bool = True


@dataclass(frozen=True)
class TerrainSpec:
    """Specification for a terrain type (from canonical catalog)."""
    terrain_type: TerrainType
    environment_class: EnvironmentClass
    solo_access: Dict[str, str]          # MobilityClass -> "pass"|"deny"
    joint_access: List[JointAccessRule]
    default_visibility_factor: float
    default_comm_factor: float
    default_risk_rate: float


@dataclass(frozen=True)
class TransitionSpec:
    """Specification for a transition type."""
    transition_type: TransitionType
    connects: List[str]                  # List of EnvironmentClass values (length 2)


@dataclass(frozen=True)
class TeamModeSpec:
    """Specification for a cooperative teaming mode."""
    mode: TeamMode
    actor_required: bool
    passenger_required: bool
    speed_multiplier: float
    energy_multiplier: float
    active_capabilities: str             # "actor_only" | "both"
    detach_requires_node: bool
    actor_mobility_class: Optional[str] = None
    passenger_mobility_class: Optional[str] = None


@dataclass(frozen=True)
class PayloadSpec:
    """Payload capacity specification for a unit type."""
    mass_capacity: float
    volume_capacity: float
    allowed_payload_tags: List[str]


@dataclass(frozen=True)
class EnergySpec:
    """Energy model for a unit type."""
    capacity: float
    recharge_rate: float
    idle_cost_per_tick: float
    move_cost_per_distance: Dict[str, float]  # TerrainType -> cost per metre
    action_costs: Dict[str, float]            # ActionType -> energy cost


@dataclass(frozen=True)
class SensingSpec:
    """Sensing capability specification for a unit type."""
    range: float
    durations: Dict[str, int]    # AssessmentMode -> ticks
    base_quality: float


@dataclass(frozen=True)
class CommunicationSpec:
    """Communication capability specification for a unit type."""
    range: float
    relay_capable: bool
    relay_bonus: float


@dataclass(frozen=True)
class PeerTransportSpec:
    """Peer transport specification for a unit type."""
    can_host_modes: List[str]        # TeamMode values
    can_be_passenger_modes: List[str]
    passenger_mass_capacity: float
    passenger_size_limit: str        # SizeClass value


@dataclass(frozen=True)
class UnitTypeSpec:
    """Full specification for a canonical unit type."""
    unit_type_id: UnitTypeId
    role_tags: List[str]
    mobility_class: MobilityClass
    size_class: SizeClass
    mass: float
    speed_by_terrain: Dict[str, float]   # TerrainType -> speed (m/tick)
    payload: PayloadSpec
    energy: EnergySpec
    sensing: SensingSpec
    communication: CommunicationSpec
    capabilities: List[str]              # ActionType values
    peer_transport: PeerTransportSpec
    capability_rates: Dict[str, float] = field(default_factory=dict)


@dataclass(frozen=True)
class ObjectTypeSpec:
    """Full specification for a canonical object type."""
    object_type_id: ObjectTypeId
    object_class: str           # "cargo" | "tool" | "component"
    mass: float
    volume: float
    handling_tags: List[str]
    pickable: bool
    droppable: bool
    installable: bool
    consumable: bool


# ---------------------------------------------------------------------------
# Graph data types
# ---------------------------------------------------------------------------

@dataclass
class GraphNode:
    """A node (location) in the CIMO metric graph."""
    node_id: NodeId
    label: str
    environment_class: EnvironmentClass
    x: float = 0.0
    y: float = 0.0
    z: float = 0.0
    is_recharge_point: bool = False
    metadata: Dict = field(default_factory=dict)


@dataclass
class GraphEdge:
    """A directed edge in the CIMO metric graph."""
    edge_id: EdgeId
    source: NodeId
    target: NodeId
    terrain_type: TerrainType
    distance: float                      # metres
    transition_type: Optional[TransitionType] = None
    is_operable: bool = True             # can be blocked by disturbances
    metadata: Dict = field(default_factory=dict)


# ---------------------------------------------------------------------------
# Unit / Object instance data types (runtime mutable; use @dataclass without frozen)
# ---------------------------------------------------------------------------

@dataclass
class UnitInstance:
    """Runtime instance of a unit."""
    unit_id: UnitId
    unit_type_id: UnitTypeId
    spec: UnitTypeSpec
    location: NodeId
    energy: float
    payload_items: List[ObjectId] = field(default_factory=list)
    team_partner: Optional[UnitId] = None
    team_mode: Optional[TeamMode] = None
    is_actor: bool = True               # True=actor, False=passenger
    busy_until: Tick = Tick(0)          # tick when current action ends
    current_action_id: Optional[ActionId] = None
    is_active: bool = True
    risk_accumulated: float = 0.0
    metadata: Dict = field(default_factory=dict)


@dataclass
class ObjectInstance:
    """Runtime instance of an object."""
    object_id: ObjectId
    object_type_id: ObjectTypeId
    spec: ObjectTypeSpec
    location: Optional[NodeId]          # None if carried by a unit
    carried_by: Optional[UnitId] = None
    installed_at: Optional[TargetId] = None
    is_consumed: bool = False
    metadata: Dict = field(default_factory=dict)


# ---------------------------------------------------------------------------
# Action request / result data types
# ---------------------------------------------------------------------------

@dataclass
class ActionRequest:
    """A primitive action request submitted to CIMO-Core."""
    action_id: ActionId
    action_type: ActionType
    actor_id: UnitId
    tick_submitted: Tick
    # Optional fields depending on action type
    target_node: Optional[NodeId] = None
    target_edge: Optional[EdgeId] = None
    object_id: Optional[ObjectId] = None
    target_id: Optional[TargetId] = None
    mission_id: Optional[MissionId] = None
    passenger_id: Optional[UnitId] = None
    team_mode: Optional[TeamMode] = None
    duration: Optional[int] = None
    assessment_mode: Optional[AssessmentMode] = None
    metadata: Dict = field(default_factory=dict)


@dataclass
class ActionResult:
    """Result of processing an action request."""
    action_id: ActionId
    accepted: bool
    reject_reason: Optional[str] = None   # ReasonCode value
    scheduled_start: Optional[Tick] = None
    scheduled_end: Optional[Tick] = None
    metadata: Dict = field(default_factory=dict)


# ---------------------------------------------------------------------------
# Mission / dependency data types
# ---------------------------------------------------------------------------

@dataclass
class MissionDependency:
    """Dependency between two missions."""
    dependency_type: MissionDependencyType
    from_mission: MissionId
    to_mission: MissionId


@dataclass
class MissionSpec:
    """A mission in the workload."""
    mission_id: MissionId
    family: MissionFamily
    priority: Priority
    release_tick: Tick
    deadline_tick: Optional[Tick]
    connectivity_requirement: ConnectivityRequirement
    risk_budget: float
    assigned_units: List[UnitId] = field(default_factory=list)
    dependencies: List[MissionDependency] = field(default_factory=list)
    # Family-specific parameters stored as free dict
    params: Dict = field(default_factory=dict)
    metadata: Dict = field(default_factory=dict)


# ---------------------------------------------------------------------------
# Disturbance data types
# ---------------------------------------------------------------------------

@dataclass
class DisturbanceSpec:
    """A disturbance definition."""
    disturbance_id: DisturbanceId
    trigger_tick: Tick
    resolve_tick: Optional[Tick]
    affected_edges: List[EdgeId] = field(default_factory=list)
    affected_nodes: List[NodeId] = field(default_factory=list)
    effect: str = "block"               # "block" | "slow" | "degrade_comm"
    magnitude: float = 1.0
    metadata: Dict = field(default_factory=dict)


# ---------------------------------------------------------------------------
# Metric bundle — 5 指标族
# ---------------------------------------------------------------------------

@dataclass
class TaskCompletionMetrics:
    """Indicator Group 1 — Task Completion (§8.1)."""
    missions_total: int
    missions_completed: int
    missions_violated: int
    missions_expired: int
    completion_rate: float           # missions_completed / missions_total
    violation_rate: float            # missions_violated / missions_total
    mean_mission_latency: float      # mean ticks from release to completion
    per_mission: Dict[str, Dict] = field(default_factory=dict)


@dataclass
class EfficiencyMetrics:
    """Indicator Group 2 — Efficiency (§8.2)."""
    total_energy_consumed: float
    total_distance_travelled: float
    per_unit: Dict[str, Dict] = field(default_factory=dict)


@dataclass
class CoverageConnectivityMetrics:
    """Indicator Group 3 — Coverage & Connectivity (§8.3)."""
    coverage_fraction: float         # fraction of coverage targets currently covered
    relay_connectivity_fraction: float  # fraction of ticks all relays were connected


@dataclass
class RiskMetrics:
    """Indicator Group 4 — Risk (§8.4)."""
    total_risk_accumulated: float
    per_unit: Dict[str, float] = field(default_factory=dict)


@dataclass
class CompositeScore:
    """Indicator Group 5 — Composite weighted score (§8.5)."""
    score: float                     # 0–1 overall score
    weights: Dict[str, float] = field(default_factory=dict)
    components: Dict[str, float] = field(default_factory=dict)


@dataclass
class MetricBundle:
    """Structured metric bundle output by CIMO-Core at episode end.

    Top-level flat fields are kept for backward compatibility.
    The five indicator groups are available under the ``groups`` field.
    """
    scenario_id: str
    total_ticks: int
    # Flat backward-compat fields
    missions_completed: int
    missions_violated: int
    missions_expired: int
    total_energy_consumed: float
    total_distance_travelled: float
    total_risk_accumulated: float
    mean_mission_latency: float
    coverage_fraction: float
    relay_connectivity_fraction: float
    # 5 indicator groups
    task_completion: TaskCompletionMetrics = field(
        default_factory=lambda: TaskCompletionMetrics(0, 0, 0, 0, 0.0, 0.0, 0.0)
    )
    efficiency: EfficiencyMetrics = field(
        default_factory=lambda: EfficiencyMetrics(0.0, 0.0)
    )
    coverage_connectivity: CoverageConnectivityMetrics = field(
        default_factory=lambda: CoverageConnectivityMetrics(0.0, 0.0)
    )
    risk: RiskMetrics = field(
        default_factory=lambda: RiskMetrics(0.0)
    )
    composite: CompositeScore = field(
        default_factory=lambda: CompositeScore(0.0)
    )
    # Legacy per-entity dicts (also embedded in groups above)
    per_unit_metrics: Dict[str, Dict] = field(default_factory=dict)
    per_mission_metrics: Dict[str, Dict] = field(default_factory=dict)
    metadata: Dict = field(default_factory=dict)
