"""
Checkpoint system for CIMO v1.

Checkpoints capture the full serialisable state at a given tick.
They are saved as JSON (.json) files and can be used to:
- Resume a paused episode.
- Validate state at key scenario milestones.
"""

from __future__ import annotations

import json
from dataclasses import asdict
from pathlib import Path
from typing import Any, Dict, Optional

from cimo.core import events as ev
from cimo.core.ids import CheckpointId, Tick
from cimo.core.state import RuntimeState


def capture_checkpoint(
    state: RuntimeState,
    checkpoint_id: CheckpointId,
    description: str = "",
) -> Dict[str, Any]:
    """
    Capture the current runtime state as a serialisable checkpoint dict.

    The checkpoint includes:
    - Scenario metadata (scenario_id, seed, tick).
    - Unit states (location, energy, payload, team).
    - Object states (location, carried_by).
    - Target states.
    - Mission statuses.
    - Disturbance states.
    - Metric accumulators.
    """
    units_snap = {}
    for uid, unit in state.units.items():
        units_snap[uid] = {
            "unit_type_id": unit.unit_type_id,
            "location": unit.location,
            "energy": unit.energy,
            "payload_items": list(unit.payload_items),
            "team_partner": unit.team_partner,
            "team_mode": unit.team_mode.value if unit.team_mode else None,
            "is_actor": unit.is_actor,
            "risk_accumulated": unit.risk_accumulated,
        }

    objects_snap = {}
    for oid, obj in state.objects.items():
        objects_snap[oid] = {
            "object_type_id": obj.object_type_id,
            "location": obj.location,
            "carried_by": obj.carried_by,
            "installed_at": obj.installed_at,
            "is_consumed": obj.is_consumed,
        }

    targets_snap = {}
    for tid, tgt in state.targets.items():
        targets_snap[tid] = {
            "target_type": tgt.target_type,
            "location": tgt.location,
            "assessment_state": tgt.assessment_state,
            "assessment_quality": tgt.assessment_quality,
            "access_operable": tgt.access_operable,
            "service_active": tgt.service_active,
            "service_progress": tgt.service_progress,
            "coverage_active": tgt.coverage_active,
        }

    missions_snap = {}
    for mid, ms in state.missions.items():
        missions_snap[mid] = {
            "status": ms.status,
            "released_at": int(ms.released_at) if ms.released_at else None,
            "completed_at": int(ms.completed_at) if ms.completed_at else None,
            "risk_used": ms.risk_used,
        }

    disturbances_snap = {}
    for did, ds in state.disturbances.items():
        disturbances_snap[did] = {
            "is_active": ds.is_active,
            "triggered_at": int(ds.triggered_at) if ds.triggered_at else None,
            "resolved_at": int(ds.resolved_at) if ds.resolved_at else None,
        }

    checkpoint = {
        "checkpoint_id": checkpoint_id,
        "description": description,
        "scenario_id": state.scenario_id,
        "tick": int(state.current_tick),
        "seed": state.seed,
        "units": units_snap,
        "objects": objects_snap,
        "targets": targets_snap,
        "missions": missions_snap,
        "disturbances": disturbances_snap,
        "metrics": {
            "total_energy_consumed": state.total_energy_consumed,
            "total_distance_travelled": state.total_distance_travelled,
            "total_risk_accumulated": state.total_risk_accumulated,
            "missions_completed": state.missions_completed,
            "missions_violated": state.missions_violated,
            "missions_expired": state.missions_expired,
        },
    }

    # Emit checkpoint event
    state.event_log.append(ev.checkpoint_event(
        state.current_tick, checkpoint_id, {"description": description}
    ))

    return checkpoint


def save_checkpoint(checkpoint: Dict[str, Any], path: Path) -> None:
    """Save a checkpoint dict to a JSON file."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(checkpoint, indent=2), encoding="utf-8")


def load_checkpoint(path: Path) -> Dict[str, Any]:
    """Load a checkpoint dict from a JSON file."""
    return json.loads(path.read_text(encoding="utf-8"))
