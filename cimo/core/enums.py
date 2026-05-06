"""
Frozen enumerations for CIMO v1.
All enums are defined here and must not be modified after v1 freeze.
"""

from enum import Enum


class EnvironmentClass(str, Enum):
    """4.1 Environment classification."""
    outdoor = "outdoor"
    indoor = "indoor"
    subterranean = "subterranean"
    airspace = "airspace"
    interface = "interface"


class TerrainType(str, Enum):
    """4.2 Terrain type for edges in the metric graph."""
    open_yard = "open_yard"
    road_lane = "road_lane"
    indoor_corridor = "indoor_corridor"
    room_access = "room_access"
    river_gap = "river_gap"
    cave_tunnel = "cave_tunnel"
    stairs_ramp = "stairs_ramp"
    rubble_passage = "rubble_passage"
    air_route = "air_route"


class TransitionType(str, Enum):
    """4.3 Transition type for node-to-node interface connections."""
    doorway = "doorway"
    gate = "gate"
    bridge = "bridge"
    tunnel_portal = "tunnel_portal"
    loading_dock = "loading_dock"
    shaft_or_vertical_link = "shaft_or_vertical_link"


class MobilityClass(str, Enum):
    """4.4 Mobility class of a unit."""
    air = "air"
    ground_light = "ground_light"
    ground_heavy = "ground_heavy"


class SizeClass(str, Enum):
    """4.5 Physical size class of a unit or object."""
    small = "small"
    medium = "medium"
    large = "large"


class TeamMode(str, Enum):
    """4.6 Cooperative teaming mode between two units."""
    independent = "independent"
    airlift = "airlift"
    mounted_transit = "mounted_transit"
    tow = "tow"


class UnitTypeId(str, Enum):
    """4.7 Canonical unit type identifiers."""
    aerial_scout = "aerial_scout"
    inspection_rover = "inspection_rover"
    ground_courier = "ground_courier"
    heavy_tugger = "heavy_tugger"
    service_manipulator = "service_manipulator"
    mobile_relay = "mobile_relay"


class ObjectTypeId(str, Enum):
    """4.8 Canonical object type identifiers."""
    cargo_item = "cargo_item"
    toolkit = "toolkit"
    component_module = "component_module"


class MissionFamily(str, Enum):
    """4.9 High-level mission family / template."""
    relocate_object = "relocate_object"
    relocate_unit = "relocate_unit"
    assess_target = "assess_target"
    enable_access = "enable_access"
    restore_service = "restore_service"
    maintain_coverage = "maintain_coverage"
    recover_unit = "recover_unit"


class AssessmentMode(str, Enum):
    """4.10 Assessment mode for inspect/verify/diagnose actions."""
    inspect = "inspect"
    verify = "verify"
    diagnose = "diagnose"


class CoverageMode(str, Enum):
    """4.11 Coverage mode for maintain_coverage missions."""
    sensing = "sensing"
    communication = "communication"


class Priority(str, Enum):
    """4.12 Mission or task priority."""
    low = "low"
    medium = "medium"
    high = "high"


class ConnectivityRequirement(str, Enum):
    """4.13 Connectivity requirement for missions."""
    none = "none"
    start_end = "start_end"
    continuous = "continuous"


class MissionDependencyType(str, Enum):
    """4.14 Dependency relationship between missions."""
    finish_before_start = "finish_before_start"
    guard_during = "guard_during"
    shared_deadline = "shared_deadline"
    mutex = "mutex"


class ActionType(str, Enum):
    """4.15 Primitive action types accepted by CIMO-Core."""
    traverse = "traverse"
    wait = "wait"
    pick = "pick"
    drop = "drop"
    inspect = "inspect"
    monitor = "monitor"
    repair = "repair"
    clear_blockage = "clear_blockage"
    deploy_relay = "deploy_relay"
    recharge = "recharge"
    attach = "attach"
    detach = "detach"


class EventType(str, Enum):
    """4.16 Typed events emitted by the CIMO-Core runtime."""
    action_request = "action_request"
    action_accept = "action_accept"
    action_reject = "action_reject"
    action_start = "action_start"
    action_complete = "action_complete"
    action_fail = "action_fail"
    action_abort = "action_abort"
    attach = "attach"
    detach = "detach"
    pick = "pick"
    drop = "drop"
    install = "install"
    consume = "consume"
    assessment_state_change = "assessment_state_change"
    access_state_change = "access_state_change"
    service_state_change = "service_state_change"
    coverage_start = "coverage_start"
    coverage_end = "coverage_end"
    connectivity_state_change = "connectivity_state_change"
    mission_release = "mission_release"
    mission_complete = "mission_complete"
    mission_violate = "mission_violate"
    mission_expire = "mission_expire"
    disturbance_trigger = "disturbance_trigger"
    disturbance_resolve = "disturbance_resolve"
    checkpoint = "checkpoint"


class ReasonCode(str, Enum):
    """4.17 Reason codes for action rejection or failure."""
    missing_capability = "missing_capability"
    missing_required_object = "missing_required_object"
    incompatible_team_mode = "incompatible_team_mode"
    access_not_operable = "access_not_operable"
    target_not_verified = "target_not_verified"
    connectivity_violation = "connectivity_violation"
    risk_budget_exceeded = "risk_budget_exceeded"
    deadline_missed = "deadline_missed"
    capacity_conflict = "capacity_conflict"
    energy_depleted = "energy_depleted"
    invalid_detach_location = "invalid_detach_location"
    disturbance_blocked_execution = "disturbance_blocked_execution"
    target_state_precondition_unsatisfied = "target_state_precondition_unsatisfied"
    invalid_target_type = "invalid_target_type"
    not_colocated = "not_colocated"
    out_of_range = "out_of_range"
    busy_actor = "busy_actor"
    missing_passenger = "missing_passenger"
    invalid_mode_for_actor = "invalid_mode_for_actor"
    invalid_mode_for_passenger = "invalid_mode_for_passenger"
