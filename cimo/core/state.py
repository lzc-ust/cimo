"""
Runtime state for CIMO v1.
RuntimeState is the single mutable container that holds all live simulation
state.  It is updated by the scheduler / action processor each tick.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional, Set

from cimo.core.datatypes import (
    DisturbanceSpec,
    MetricBundle,
    MissionSpec,
    ObjectInstance,
    UnitInstance,
)
from cimo.core.ledger import MissionLedger
from cimo.core.enums import MissionFamily, Priority
from cimo.core.graph import MetricGraph
from cimo.core.ids import (
    ActionId,
    DisturbanceId,
    EdgeId,
    MissionId,
    NodeId,
    ObjectId,
    TargetId,
    Tick,
    UnitId,
)


# ---------------------------------------------------------------------------
# Target state
# ---------------------------------------------------------------------------

@dataclass
class TargetState:
    """Runtime state of an assessment / service / access target."""
    target_id: TargetId
    target_type: str                 # "assessment" | "access" | "service" | "coverage"
    location: NodeId
    # Assessment
    assessment_state: str = "unknown"   # "unknown" | "inspected" | "verified" | "diagnosed"
    assessment_quality: float = 0.0
    # Access
    access_operable: bool = True
    # Service
    service_active: bool = False
    service_progress: float = 0.0
    # Coverage
    coverage_active: bool = False
    # Metadata
    metadata: Dict = field(default_factory=dict)


# ---------------------------------------------------------------------------
# Mission runtime state
# ---------------------------------------------------------------------------

@dataclass
class MissionState:
    """Runtime tracking of a single mission."""
    mission_id: MissionId
    spec: MissionSpec
    status: str = "pending"          # pending | active | complete | violated | expired
    released_at: Optional[Tick] = None
    completed_at: Optional[Tick] = None
    violated_at: Optional[Tick] = None
    expired_at: Optional[Tick] = None
    risk_used: float = 0.0
    sub_task_progress: Dict = field(default_factory=dict)


# ---------------------------------------------------------------------------
# Disturbance runtime state
# ---------------------------------------------------------------------------

@dataclass
class DisturbanceState:
    """Runtime tracking of a disturbance."""
    disturbance_id: DisturbanceId
    spec: DisturbanceSpec
    is_active: bool = False
    triggered_at: Optional[Tick] = None
    resolved_at: Optional[Tick] = None


# ---------------------------------------------------------------------------
# Active action tracking
# ---------------------------------------------------------------------------

@dataclass
class ActiveAction:
    """An in-flight action being executed."""
    action_id: ActionId
    actor_id: UnitId
    action_type: str            # ActionType value
    start_tick: Tick
    end_tick: Tick
    params: Dict = field(default_factory=dict)


# ---------------------------------------------------------------------------
# RuntimeState
# ---------------------------------------------------------------------------

@dataclass
class RuntimeState:
    """
    Complete mutable runtime state of a CIMO episode.

    All sub-systems (scheduler, actions, missions, disturbances, metrics)
    read and write through this object.
    """
    # Scenario identity
    scenario_id: str = ""
    current_tick: Tick = Tick(0)
    max_ticks: int = 10_000
    episode_done: bool = False
    seed: int = 0

    # World graph
    graph: MetricGraph = field(default_factory=MetricGraph)

    # Entities
    units: Dict[UnitId, UnitInstance] = field(default_factory=dict)
    objects: Dict[ObjectId, ObjectInstance] = field(default_factory=dict)
    targets: Dict[TargetId, TargetState] = field(default_factory=dict)

    # Workload
    missions: Dict[MissionId, MissionState] = field(default_factory=dict)
    mission_order: List[MissionId] = field(default_factory=list)  # insertion order

    # Disturbances
    disturbances: Dict[DisturbanceId, DisturbanceState] = field(default_factory=dict)

    # In-flight actions (unit_id -> ActiveAction)
    active_actions: Dict[UnitId, ActiveAction] = field(default_factory=dict)

    # Event log (accumulated this episode; events.py appends here)
    event_log: List[Dict] = field(default_factory=list)

    # Periodic state records (for replay)
    state_records: List[Dict] = field(default_factory=list)
    record_interval: int = 10          # ticks between state snapshots

    # Metric accumulators
    total_energy_consumed: float = 0.0
    total_distance_travelled: float = 0.0
    total_risk_accumulated: float = 0.0
    missions_completed: int = 0
    missions_violated: int = 0
    missions_expired: int = 0
    mission_latencies: List[float] = field(default_factory=list)

    # Coverage tracking
    coverage_ticks: int = 0
    coverage_total_ticks: int = 0
    relay_connected_ticks: int = 0
    relay_total_ticks: int = 0

    # Per-unit accumulators
    unit_energy: Dict[UnitId, float] = field(default_factory=dict)
    unit_distance: Dict[UnitId, float] = field(default_factory=dict)
    unit_risk: Dict[UnitId, float] = field(default_factory=dict)

    # Per-mission completion info
    mission_completion_ticks: Dict[MissionId, Tick] = field(default_factory=dict)

    # Mission ledger — records structured outcomes of all missions/actions
    ledger: MissionLedger = field(default_factory=MissionLedger)

    def is_unit_busy(self, unit_id: UnitId) -> bool:
        """Return True if the unit has an in-flight action."""
        return unit_id in self.active_actions

    def get_unit(self, unit_id: UnitId) -> Optional[UnitInstance]:
        return self.units.get(unit_id)

    def get_mission_state(self, mission_id: MissionId) -> Optional[MissionState]:
        return self.missions.get(mission_id)

    def tick_advance(self) -> None:
        """Advance the simulation clock by one tick."""
        self.current_tick = Tick(self.current_tick + 1)
        if self.current_tick >= self.max_ticks:
            self.episode_done = True
