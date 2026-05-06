"""
Action execution logic for CIMO v1.

This module contains:
- ActionProcessor: validates and schedules primitive action requests.
- _execute_*: per-action completion handlers called by the scheduler.

CIMO-Core accepts only primitive actions (ActionType enum).
All validation happens before scheduling; rejection reasons use ReasonCode.
"""

from __future__ import annotations

import uuid
from typing import Dict, List, Optional, Tuple

from cimo.core import events as ev
from cimo.core.datatypes import ActionRequest, ActionResult, UnitTypeSpec
from cimo.core.state import ActiveAction
from cimo.core.enums import ActionType, ReasonCode, TeamMode
from cimo.core.ids import ActionId, NodeId, ObjectId, Tick, UnitId
from cimo.core.physics import (
    action_energy_cost,
    clamp_energy,
    idle_energy_cost,
    recharge_amount,
    traverse_energy_cost,
    traverse_time_ticks,
)
from cimo.core.state import RuntimeState


class ActionProcessor:
    """
    Validates, schedules and completes primitive action requests.

    Usage (called by the scheduler each tick):
        result = processor.submit(request, state)
        # ... on end_tick:
        processor.complete(action_id, state)
    """

    def submit(self, request: ActionRequest, state: RuntimeState) -> ActionResult:
        """
        Validate and schedule a primitive action.

        Returns ActionResult with accepted=True and scheduled times,
        or accepted=False with a ReasonCode.
        """
        unit = state.get_unit(request.actor_id)
        if unit is None:
            return ActionResult(request.action_id, False, ReasonCode.missing_capability.value)

        # Emit action_request event
        state.event_log.append(ev.action_request(
            state.current_tick, request.actor_id, request.action_id,
            request.action_type.value, {}
        ))

        # Check busy
        if state.is_unit_busy(request.actor_id):
            return self._reject(request, state, ReasonCode.busy_actor)

        # Check capability
        if request.action_type.value not in unit.spec.capabilities:
            return self._reject(request, state, ReasonCode.missing_capability)

        # Dispatch to per-action validator
        handler = _VALIDATORS.get(request.action_type)
        if handler:
            reason = handler(request, state)
            if reason:
                return self._reject(request, state, reason)

        # Compute duration
        duration = _compute_duration(request, state)
        start_tick = Tick(state.current_tick)
        end_tick = Tick(state.current_tick + duration)

        # Schedule
        active = ActiveAction(
            action_id=request.action_id,
            actor_id=request.actor_id,
            action_type=request.action_type.value,
            start_tick=start_tick,
            end_tick=end_tick,
            params=_extract_params(request),
        )
        state.active_actions[request.actor_id] = active
        unit.current_action_id = request.action_id
        unit.busy_until = end_tick

        # Emit accept
        state.event_log.append(ev.action_accept(
            state.current_tick, request.actor_id, request.action_id,
            int(start_tick), int(end_tick)
        ))
        state.event_log.append(ev.action_start(
            state.current_tick, request.actor_id, request.action_id
        ))

        return ActionResult(
            action_id=request.action_id,
            accepted=True,
            scheduled_start=start_tick,
            scheduled_end=end_tick,
        )

    def _reject(self, request: ActionRequest, state: RuntimeState, reason: ReasonCode) -> ActionResult:
        state.event_log.append(ev.action_reject(
            state.current_tick, request.actor_id, request.action_id, reason
        ))
        return ActionResult(request.action_id, False, reason.value)

    def complete(self, actor_id: UnitId, state: RuntimeState) -> None:
        """Called by the scheduler when an action's end_tick is reached."""
        active = state.active_actions.get(actor_id)
        if active is None:
            return

        handler = _COMPLETERS.get(active.action_type)
        if handler:
            success, reason = handler(active, state)
        else:
            success, reason = True, None

        if success:
            state.event_log.append(ev.action_complete(
                state.current_tick, actor_id, active.action_id
            ))
        else:
            state.event_log.append(ev.action_fail(
                state.current_tick, actor_id, active.action_id,
                reason or ReasonCode.missing_capability
            ))

        # Free the unit
        unit = state.get_unit(actor_id)
        if unit:
            unit.current_action_id = None
        del state.active_actions[actor_id]


# ---------------------------------------------------------------------------
# Validators (return ReasonCode or None if valid)
# ---------------------------------------------------------------------------

def _validate_traverse(request: ActionRequest, state: RuntimeState) -> Optional[ReasonCode]:
    unit = state.get_unit(request.actor_id)
    target_node = request.target_node
    if target_node is None:
        return ReasonCode.missing_capability

    edge = state.graph.edge_between(unit.location, target_node)
    if edge is None:
        return ReasonCode.missing_capability

    if not edge.is_operable:
        return ReasonCode.disturbance_blocked_execution

    # Solo or joint access
    if unit.team_mode and unit.team_mode != TeamMode.independent and unit.team_partner:
        partner = state.get_unit(unit.team_partner)
        if partner is None:
            return ReasonCode.missing_passenger
        from cimo.core.enums import MobilityClass
        ok = state.graph.can_joint_traverse(
            edge,
            unit.spec.mobility_class,
            partner.spec.mobility_class,
            unit.team_mode,
        )
    else:
        ok = state.graph.can_solo_traverse(edge, unit.spec.mobility_class)

    if not ok:
        return ReasonCode.incompatible_team_mode

    # Energy check (rough)
    terrain_spec = state.graph._terrain_specs.get(edge.terrain_type.value)
    team_mode_spec = None
    if unit.team_mode and unit.team_mode != TeamMode.independent:
        from cimo.core.catalogs import TEAM_MODE_SPECS
        team_mode_spec = TEAM_MODE_SPECS.get(unit.team_mode.value)
    cost = traverse_energy_cost(unit.spec, edge, team_mode_spec)
    if unit.energy < cost * 0.5:  # allow some slack for idle cost
        return ReasonCode.energy_depleted

    return None


def _validate_pick(request: ActionRequest, state: RuntimeState) -> Optional[ReasonCode]:
    unit = state.get_unit(request.actor_id)
    obj_id = request.object_id
    if obj_id is None:
        return ReasonCode.missing_required_object
    obj = state.objects.get(obj_id)
    if obj is None or not obj.spec.pickable:
        return ReasonCode.missing_required_object
    if obj.location != unit.location:
        return ReasonCode.not_colocated
    # Payload capacity
    current_mass = sum(
        state.objects[oid].spec.mass
        for oid in unit.payload_items
        if oid in state.objects
    )
    if current_mass + obj.spec.mass > unit.spec.payload.mass_capacity:
        return ReasonCode.capacity_conflict
    # Tag check
    for tag in obj.spec.handling_tags:
        if tag in unit.spec.payload.allowed_payload_tags:
            return None
    return ReasonCode.incompatible_team_mode  # no matching tag


def _validate_drop(request: ActionRequest, state: RuntimeState) -> Optional[ReasonCode]:
    unit = state.get_unit(request.actor_id)
    obj_id = request.object_id
    if obj_id is None or obj_id not in unit.payload_items:
        return ReasonCode.missing_required_object
    return None


def _validate_inspect(request: ActionRequest, state: RuntimeState) -> Optional[ReasonCode]:
    unit = state.get_unit(request.actor_id)
    target_id = request.target_id
    if target_id is None:
        return ReasonCode.invalid_target_type
    target = state.targets.get(target_id)
    if target is None:
        return ReasonCode.invalid_target_type
    # Range check
    from cimo.core.sensing import can_sense_target
    node_positions = {
        n.node_id: (n.x, n.y, n.z)
        for n in state.graph.nodes()
    }
    terrain_spec = state.graph._terrain_specs.get(
        state.graph.get_node(unit.location).environment_class.value
        if state.graph.get_node(unit.location) else "outdoor",
        None,
    )
    vis_factor = terrain_spec.default_visibility_factor if terrain_spec else 1.0
    ok = can_sense_target(
        unit.location, target.location, unit.spec.sensing, node_positions, vis_factor
    )
    if not ok:
        return ReasonCode.out_of_range
    return None


def _validate_attach(request: ActionRequest, state: RuntimeState) -> Optional[ReasonCode]:
    unit = state.get_unit(request.actor_id)
    passenger_id = request.passenger_id
    mode = request.team_mode
    if passenger_id is None or mode is None:
        return ReasonCode.missing_passenger
    passenger = state.get_unit(passenger_id)
    if passenger is None:
        return ReasonCode.missing_passenger
    if passenger.location != unit.location:
        return ReasonCode.not_colocated
    if state.is_unit_busy(passenger_id):
        return ReasonCode.busy_actor
    # Mode compatibility
    if mode.value not in unit.spec.peer_transport.can_host_modes:
        return ReasonCode.invalid_mode_for_actor
    if mode.value not in passenger.spec.peer_transport.can_be_passenger_modes:
        return ReasonCode.invalid_mode_for_passenger
    # Mass check
    if passenger.spec.mass > unit.spec.peer_transport.passenger_mass_capacity:
        return ReasonCode.capacity_conflict
    return None


def _validate_detach(request: ActionRequest, state: RuntimeState) -> Optional[ReasonCode]:
    unit = state.get_unit(request.actor_id)
    if unit.team_partner is None:
        return ReasonCode.missing_passenger
    # detach_requires_node: must be at a node (always true in discrete model)
    return None


def _validate_recharge(request: ActionRequest, state: RuntimeState) -> Optional[ReasonCode]:
    unit = state.get_unit(request.actor_id)
    node = state.graph.get_node(unit.location)
    if node is None or not node.is_recharge_point:
        return ReasonCode.access_not_operable
    return None


_VALIDATORS: Dict[ActionType, callable] = {
    ActionType.traverse: _validate_traverse,
    ActionType.pick: _validate_pick,
    ActionType.drop: _validate_drop,
    ActionType.inspect: _validate_inspect,
    ActionType.monitor: _validate_inspect,   # same range check
    ActionType.attach: _validate_attach,
    ActionType.detach: _validate_detach,
    ActionType.recharge: _validate_recharge,
}


# ---------------------------------------------------------------------------
# Duration computation
# ---------------------------------------------------------------------------

def _compute_duration(request: ActionRequest, state: RuntimeState) -> int:
    unit = state.get_unit(request.actor_id)

    if request.action_type == ActionType.traverse:
        edge = state.graph.edge_between(unit.location, request.target_node)
        if edge is None:
            return 1
        team_mode_spec = None
        if unit.team_mode and unit.team_mode != TeamMode.independent:
            from cimo.core.catalogs import TEAM_MODE_SPECS
            team_mode_spec = TEAM_MODE_SPECS.get(unit.team_mode.value)
        return traverse_time_ticks(unit.spec, edge, team_mode_spec)

    if request.action_type in (ActionType.inspect, ActionType.monitor):
        mode = request.assessment_mode
        if mode:
            return unit.spec.sensing.durations.get(mode.value, 5)
        return unit.spec.sensing.durations.get("inspect", 5)

    if request.action_type == ActionType.recharge:
        deficit = unit.spec.energy.capacity - unit.energy
        from cimo.core.physics import compute_recharge_ticks
        return compute_recharge_ticks(unit.spec, deficit)

    if request.action_type == ActionType.wait:
        return max(1, request.duration or 1)

    if request.action_type == ActionType.repair:
        target = state.targets.get(request.target_id) if request.target_id else None
        remaining = 1.0 - (target.service_progress if target else 0.0)
        rate = unit.spec.capability_rates.get("repair", 1.0)
        import math
        return max(1, math.ceil(remaining / rate))

    if request.action_type == ActionType.clear_blockage:
        rate = unit.spec.capability_rates.get("clear_blockage", 1.0)
        import math
        return max(1, math.ceil(1.0 / rate))

    # pick, drop, attach, detach, deploy_relay: 1 tick
    return 1


def _extract_params(request: ActionRequest) -> Dict:
    return {
        "target_node": request.target_node,
        "target_edge": request.target_edge,
        "object_id": request.object_id,
        "target_id": request.target_id,
        "mission_id": request.mission_id,
        "passenger_id": request.passenger_id,
        "team_mode": request.team_mode.value if request.team_mode else None,
        "assessment_mode": request.assessment_mode.value if request.assessment_mode else None,
    }


# ---------------------------------------------------------------------------
# Completers (return (success, reason))
# ---------------------------------------------------------------------------

def _complete_traverse(active: ActiveAction, state: RuntimeState) -> Tuple[bool, Optional[ReasonCode]]:
    unit = state.get_unit(active.actor_id)
    target_node = active.params.get("target_node")
    if not target_node:
        return False, ReasonCode.missing_capability

    edge = state.graph.edge_between(unit.location, target_node)
    if edge is None:
        return False, ReasonCode.missing_capability

    # Check edge still operable
    if not edge.is_operable:
        return False, ReasonCode.disturbance_blocked_execution

    # Deduct energy
    team_mode_spec = None
    if unit.team_mode and unit.team_mode != TeamMode.independent:
        from cimo.core.catalogs import TEAM_MODE_SPECS
        team_mode_spec = TEAM_MODE_SPECS.get(unit.team_mode.value)
    energy_cost = traverse_energy_cost(unit.spec, edge, team_mode_spec)
    unit.energy = clamp_energy(unit.energy, -energy_cost, unit.spec.energy.capacity)

    # Accumulate stats
    state.total_energy_consumed += energy_cost
    state.total_distance_travelled += edge.distance
    uid = active.actor_id
    state.unit_energy[uid] = state.unit_energy.get(uid, 0.0) + energy_cost
    state.unit_distance[uid] = state.unit_distance.get(uid, 0.0) + edge.distance

    # Risk accumulation
    terrain_spec = state.graph._terrain_specs.get(edge.terrain_type.value)
    risk_rate = terrain_spec.default_risk_rate if terrain_spec else 0.1
    from cimo.core.physics import risk_during_traverse
    ticks = active.end_tick - active.start_tick
    risk = risk_during_traverse(unit.spec, edge, risk_rate, ticks)
    unit.risk_accumulated += risk
    state.total_risk_accumulated += risk
    state.unit_risk[uid] = state.unit_risk.get(uid, 0.0) + risk

    # Move unit (and passenger if applicable)
    unit.location = target_node
    if unit.team_partner:
        partner = state.get_unit(unit.team_partner)
        if partner and unit.is_actor:
            partner.location = target_node

    return True, None


def _complete_pick(active: ActiveAction, state: RuntimeState) -> Tuple[bool, Optional[ReasonCode]]:
    unit = state.get_unit(active.actor_id)
    obj_id = active.params.get("object_id")
    obj = state.objects.get(obj_id) if obj_id else None
    if obj is None:
        return False, ReasonCode.missing_required_object
    obj.location = None
    obj.carried_by = active.actor_id
    unit.payload_items.append(obj_id)
    state.event_log.append(ev.pick_event(
        state.current_tick, active.actor_id, obj_id, unit.location
    ))
    # Energy cost
    cost = action_energy_cost(unit.spec, "pick")
    unit.energy = clamp_energy(unit.energy, -cost, unit.spec.energy.capacity)
    state.total_energy_consumed += cost
    return True, None


def _complete_drop(active: ActiveAction, state: RuntimeState) -> Tuple[bool, Optional[ReasonCode]]:
    unit = state.get_unit(active.actor_id)
    obj_id = active.params.get("object_id")
    if obj_id not in unit.payload_items:
        return False, ReasonCode.missing_required_object
    obj = state.objects.get(obj_id)
    if obj:
        obj.location = unit.location
        obj.carried_by = None
    unit.payload_items.remove(obj_id)
    state.event_log.append(ev.drop_event(
        state.current_tick, active.actor_id, obj_id, unit.location
    ))
    cost = action_energy_cost(unit.spec, "drop")
    unit.energy = clamp_energy(unit.energy, -cost, unit.spec.energy.capacity)
    state.total_energy_consumed += cost
    return True, None


def _complete_inspect(active: ActiveAction, state: RuntimeState) -> Tuple[bool, Optional[ReasonCode]]:
    unit = state.get_unit(active.actor_id)
    target_id = active.params.get("target_id")
    target = state.targets.get(target_id) if target_id else None
    if target is None:
        return False, ReasonCode.invalid_target_type
    mode = active.params.get("assessment_mode") or "inspect"
    node_positions = {n.node_id: (n.x, n.y, n.z) for n in state.graph.nodes()}
    from cimo.core.sensing import assessment_quality, _node_distance_2d
    dist = _node_distance_2d(node_positions, unit.location, target.location)
    terrain_spec = state.graph._terrain_specs.get(
        state.graph.get_node(unit.location).environment_class.value
        if state.graph.get_node(unit.location) else "outdoor", None
    )
    vis_factor = terrain_spec.default_visibility_factor if terrain_spec else 1.0
    quality = assessment_quality(unit.spec.sensing, dist, vis_factor)
    target.assessment_state = mode
    target.assessment_quality = quality
    state.event_log.append(ev.assessment_state_change(
        state.current_tick, target_id, mode, quality
    ))
    cost = action_energy_cost(unit.spec, mode)
    unit.energy = clamp_energy(unit.energy, -cost, unit.spec.energy.capacity)
    state.total_energy_consumed += cost
    return True, None


def _complete_recharge(active: ActiveAction, state: RuntimeState) -> Tuple[bool, Optional[ReasonCode]]:
    unit = state.get_unit(active.actor_id)
    ticks = active.end_tick - active.start_tick
    gained = recharge_amount(unit.spec, ticks)
    unit.energy = clamp_energy(unit.energy, gained, unit.spec.energy.capacity)
    return True, None


def _complete_attach(active: ActiveAction, state: RuntimeState) -> Tuple[bool, Optional[ReasonCode]]:
    unit = state.get_unit(active.actor_id)
    passenger_id = active.params.get("passenger_id")
    mode_str = active.params.get("team_mode")
    if passenger_id is None or mode_str is None:
        return False, ReasonCode.missing_passenger
    mode = TeamMode(mode_str)
    passenger = state.get_unit(passenger_id)
    if passenger is None:
        return False, ReasonCode.missing_passenger
    unit.team_partner = passenger_id
    unit.team_mode = mode
    unit.is_actor = True
    passenger.team_partner = active.actor_id
    passenger.team_mode = mode
    passenger.is_actor = False
    state.event_log.append(ev.attach_event(
        state.current_tick, active.actor_id, passenger_id, mode_str
    ))
    cost = action_energy_cost(unit.spec, "attach")
    unit.energy = clamp_energy(unit.energy, -cost, unit.spec.energy.capacity)
    state.total_energy_consumed += cost
    return True, None


def _complete_detach(active: ActiveAction, state: RuntimeState) -> Tuple[bool, Optional[ReasonCode]]:
    unit = state.get_unit(active.actor_id)
    passenger_id = unit.team_partner
    if passenger_id is None:
        return False, ReasonCode.missing_passenger
    passenger = state.get_unit(passenger_id)
    location = unit.location
    unit.team_partner = None
    unit.team_mode = None
    if passenger:
        passenger.team_partner = None
        passenger.team_mode = None
        passenger.is_actor = True
    state.event_log.append(ev.detach_event(
        state.current_tick, active.actor_id, passenger_id, location
    ))
    cost = action_energy_cost(unit.spec, "detach")
    unit.energy = clamp_energy(unit.energy, -cost, unit.spec.energy.capacity)
    state.total_energy_consumed += cost
    return True, None


def _complete_repair(active: ActiveAction, state: RuntimeState) -> Tuple[bool, Optional[ReasonCode]]:
    unit = state.get_unit(active.actor_id)
    target_id = active.params.get("target_id")
    target = state.targets.get(target_id) if target_id else None
    if target is None:
        return False, ReasonCode.invalid_target_type
    rate = unit.spec.capability_rates.get("repair", 1.0)
    target.service_progress = min(1.0, target.service_progress + rate)
    if target.service_progress >= 1.0:
        target.service_active = True
        state.event_log.append(ev.service_state_change(
            state.current_tick, target_id, True, target.service_progress
        ))
    cost = action_energy_cost(unit.spec, "repair")
    unit.energy = clamp_energy(unit.energy, -cost, unit.spec.energy.capacity)
    state.total_energy_consumed += cost
    return True, None


def _complete_clear_blockage(active: ActiveAction, state: RuntimeState) -> Tuple[bool, Optional[ReasonCode]]:
    unit = state.get_unit(active.actor_id)
    target_edge_id = active.params.get("target_edge")
    if target_edge_id:
        state.graph.set_edge_operable(target_edge_id, True)
        target_id = active.params.get("target_id")
        if target_id and target_id in state.targets:
            state.targets[target_id].access_operable = True
            state.event_log.append(ev.access_state_change(
                state.current_tick, target_id, True
            ))
    cost = action_energy_cost(unit.spec, "clear_blockage")
    unit.energy = clamp_energy(unit.energy, -cost, unit.spec.energy.capacity)
    state.total_energy_consumed += cost
    return True, None


def _complete_deploy_relay(active: ActiveAction, state: RuntimeState) -> Tuple[bool, Optional[ReasonCode]]:
    unit = state.get_unit(active.actor_id)
    cost = action_energy_cost(unit.spec, "deploy_relay")
    unit.energy = clamp_energy(unit.energy, -cost, unit.spec.energy.capacity)
    state.total_energy_consumed += cost
    return True, None


def _complete_monitor(active: ActiveAction, state: RuntimeState) -> Tuple[bool, Optional[ReasonCode]]:
    return _complete_inspect(active, state)


def _complete_wait(active: ActiveAction, state: RuntimeState) -> Tuple[bool, Optional[ReasonCode]]:
    unit = state.get_unit(active.actor_id)
    ticks = active.end_tick - active.start_tick
    cost = idle_energy_cost(unit.spec, ticks)
    unit.energy = clamp_energy(unit.energy, -cost, unit.spec.energy.capacity)
    state.total_energy_consumed += cost
    return True, None


_COMPLETERS: Dict[str, callable] = {
    "traverse": _complete_traverse,
    "pick": _complete_pick,
    "drop": _complete_drop,
    "inspect": _complete_inspect,
    "monitor": _complete_monitor,
    "recharge": _complete_recharge,
    "attach": _complete_attach,
    "detach": _complete_detach,
    "repair": _complete_repair,
    "clear_blockage": _complete_clear_blockage,
    "deploy_relay": _complete_deploy_relay,
    "wait": _complete_wait,
}
