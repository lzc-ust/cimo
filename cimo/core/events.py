"""
Event system for CIMO v1.

Every significant runtime occurrence is emitted as a typed event dict
and appended to the RuntimeState event_log.

Format (JSON-serialisable):
{
    "tick": <int>,
    "event_type": <EventType value>,
    "actor_id": <str | None>,
    "action_id": <str | None>,
    "mission_id": <str | None>,
    "reason": <ReasonCode value | None>,
    "payload": { ... }  # event-specific fields
}
"""

from __future__ import annotations

from typing import Any, Dict, Optional

from cimo.core.enums import EventType, ReasonCode
from cimo.core.ids import (
    ActionId, DisturbanceId, MissionId, ObjectId, TargetId, Tick, UnitId,
)


def _base(
    tick: Tick,
    event_type: EventType,
    actor_id: Optional[UnitId] = None,
    action_id: Optional[ActionId] = None,
    mission_id: Optional[MissionId] = None,
    reason: Optional[ReasonCode] = None,
) -> Dict[str, Any]:
    return {
        "tick": int(tick),
        "event_type": event_type.value,
        "actor_id": actor_id,
        "action_id": action_id,
        "mission_id": mission_id,
        "reason": reason.value if reason else None,
        "payload": {},
    }


# ---------------------------------------------------------------------------
# Action lifecycle events
# ---------------------------------------------------------------------------

def action_request(tick: Tick, actor_id: UnitId, action_id: ActionId, action_type: str, params: Dict) -> Dict:
    e = _base(tick, EventType.action_request, actor_id=actor_id, action_id=action_id)
    e["payload"] = {"action_type": action_type, **params}
    return e


def action_accept(tick: Tick, actor_id: UnitId, action_id: ActionId, start_tick: int, end_tick: int) -> Dict:
    e = _base(tick, EventType.action_accept, actor_id=actor_id, action_id=action_id)
    e["payload"] = {"start_tick": start_tick, "end_tick": end_tick}
    return e


def action_reject(tick: Tick, actor_id: UnitId, action_id: ActionId, reason: ReasonCode) -> Dict:
    e = _base(tick, EventType.action_reject, actor_id=actor_id, action_id=action_id, reason=reason)
    return e


def action_start(tick: Tick, actor_id: UnitId, action_id: ActionId) -> Dict:
    return _base(tick, EventType.action_start, actor_id=actor_id, action_id=action_id)


def action_complete(tick: Tick, actor_id: UnitId, action_id: ActionId) -> Dict:
    return _base(tick, EventType.action_complete, actor_id=actor_id, action_id=action_id)


def action_fail(tick: Tick, actor_id: UnitId, action_id: ActionId, reason: ReasonCode) -> Dict:
    e = _base(tick, EventType.action_fail, actor_id=actor_id, action_id=action_id, reason=reason)
    return e


def action_abort(tick: Tick, actor_id: UnitId, action_id: ActionId, reason: ReasonCode) -> Dict:
    e = _base(tick, EventType.action_abort, actor_id=actor_id, action_id=action_id, reason=reason)
    return e


# ---------------------------------------------------------------------------
# Object manipulation events
# ---------------------------------------------------------------------------

def pick_event(tick: Tick, actor_id: UnitId, object_id: ObjectId, location: str) -> Dict:
    e = _base(tick, EventType.pick, actor_id=actor_id)
    e["payload"] = {"object_id": object_id, "location": location}
    return e


def drop_event(tick: Tick, actor_id: UnitId, object_id: ObjectId, location: str) -> Dict:
    e = _base(tick, EventType.drop, actor_id=actor_id)
    e["payload"] = {"object_id": object_id, "location": location}
    return e


def install_event(tick: Tick, actor_id: UnitId, object_id: ObjectId, target_id: TargetId) -> Dict:
    e = _base(tick, EventType.install, actor_id=actor_id)
    e["payload"] = {"object_id": object_id, "target_id": target_id}
    return e


def consume_event(tick: Tick, actor_id: UnitId, object_id: ObjectId) -> Dict:
    e = _base(tick, EventType.consume, actor_id=actor_id)
    e["payload"] = {"object_id": object_id}
    return e


# ---------------------------------------------------------------------------
# Unit teaming events
# ---------------------------------------------------------------------------

def attach_event(tick: Tick, actor_id: UnitId, passenger_id: UnitId, mode: str) -> Dict:
    e = _base(tick, EventType.attach, actor_id=actor_id)
    e["payload"] = {"passenger_id": passenger_id, "mode": mode}
    return e


def detach_event(tick: Tick, actor_id: UnitId, passenger_id: UnitId, location: str) -> Dict:
    e = _base(tick, EventType.detach, actor_id=actor_id)
    e["payload"] = {"passenger_id": passenger_id, "location": location}
    return e


# ---------------------------------------------------------------------------
# Target state change events
# ---------------------------------------------------------------------------

def assessment_state_change(tick: Tick, target_id: TargetId, new_state: str, quality: float) -> Dict:
    e = _base(tick, EventType.assessment_state_change)
    e["payload"] = {"target_id": target_id, "new_state": new_state, "quality": quality}
    return e


def access_state_change(tick: Tick, target_id: TargetId, operable: bool) -> Dict:
    e = _base(tick, EventType.access_state_change)
    e["payload"] = {"target_id": target_id, "operable": operable}
    return e


def service_state_change(tick: Tick, target_id: TargetId, active: bool, progress: float) -> Dict:
    e = _base(tick, EventType.service_state_change)
    e["payload"] = {"target_id": target_id, "active": active, "progress": progress}
    return e


def coverage_start(tick: Tick, actor_id: UnitId, mode: str) -> Dict:
    e = _base(tick, EventType.coverage_start, actor_id=actor_id)
    e["payload"] = {"mode": mode}
    return e


def coverage_end(tick: Tick, actor_id: UnitId, mode: str) -> Dict:
    e = _base(tick, EventType.coverage_end, actor_id=actor_id)
    e["payload"] = {"mode": mode}
    return e


def connectivity_state_change(tick: Tick, connected: bool, fraction: float) -> Dict:
    e = _base(tick, EventType.connectivity_state_change)
    e["payload"] = {"connected": connected, "fraction": fraction}
    return e


# ---------------------------------------------------------------------------
# Mission lifecycle events
# ---------------------------------------------------------------------------

def mission_release(tick: Tick, mission_id: MissionId) -> Dict:
    e = _base(tick, EventType.mission_release, mission_id=mission_id)
    return e


def mission_complete(tick: Tick, mission_id: MissionId, latency: float) -> Dict:
    e = _base(tick, EventType.mission_complete, mission_id=mission_id)
    e["payload"] = {"latency": latency}
    return e


def mission_violate(tick: Tick, mission_id: MissionId, reason: ReasonCode) -> Dict:
    e = _base(tick, EventType.mission_violate, mission_id=mission_id, reason=reason)
    return e


def mission_expire(tick: Tick, mission_id: MissionId) -> Dict:
    e = _base(tick, EventType.mission_expire, mission_id=mission_id)
    return e


# ---------------------------------------------------------------------------
# Disturbance events
# ---------------------------------------------------------------------------

def disturbance_trigger(tick: Tick, disturbance_id: DisturbanceId, affected: Dict) -> Dict:
    e = _base(tick, EventType.disturbance_trigger)
    e["payload"] = {"disturbance_id": disturbance_id, **affected}
    return e


def disturbance_resolve(tick: Tick, disturbance_id: DisturbanceId) -> Dict:
    e = _base(tick, EventType.disturbance_resolve)
    e["payload"] = {"disturbance_id": disturbance_id}
    return e


# ---------------------------------------------------------------------------
# Checkpoint event
# ---------------------------------------------------------------------------

def checkpoint_event(tick: Tick, checkpoint_id: str, data: Dict) -> Dict:
    e = _base(tick, EventType.checkpoint)
    e["payload"] = {"checkpoint_id": checkpoint_id, **data}
    return e
