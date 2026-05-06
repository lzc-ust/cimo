"""
Offline runner for CIMO v1.

Runs a scenario to completion using a provided policy function
and saves:
- Event log (.jsonl)
- Metric bundle (.json)
- Checkpoint snapshots (.json)
"""

from __future__ import annotations

import json
from dataclasses import asdict
from pathlib import Path
from typing import Callable, List, Optional

from cimo.core.scheduler import RenderFn

from cimo.core.checkpoints import capture_checkpoint, save_checkpoint
from cimo.core.datatypes import ActionRequest, MetricBundle
from cimo.core.ledger import LedgerMissionEntry, MissionLedger
from cimo.core.metrics import compute_metrics
from cimo.core.replay import save_event_log
from cimo.core.scheduler import Scheduler
from cimo.core.state import RuntimeState
from cimo.sdl.compiler import compile_scenario_file


PolicyFn = Callable[[RuntimeState], List[ActionRequest]]


def run_offline(
    scenario_path: Path,
    policy_fn: Optional[PolicyFn] = None,
    output_dir: Optional[Path] = None,
    catalog_dir: Optional[Path] = None,
    checkpoint_ticks: Optional[List[int]] = None,
    render_fn: Optional[RenderFn] = None,
) -> MetricBundle:
    """
    Run a scenario to completion offline.

    Args:
        scenario_path:    Path to the .yaml scenario file.
        policy_fn:        Optional policy function (state -> list of ActionRequests).
        output_dir:       Optional directory to save outputs.
        catalog_dir:      Optional override for catalog directory.
        checkpoint_ticks: List of ticks at which to save checkpoints.
        render_fn:        Optional render callback (state -> None), called after
                          each tick.  Use this to hook in a visualiser without
                          modifying the core loop.

    Returns:
        MetricBundle with episode results.
    """
    state = compile_scenario_file(scenario_path, catalog_dir)
    scheduler = Scheduler(render_fn=render_fn)
    checkpoint_set = set(checkpoint_ticks or [])

    while not state.episode_done:
        # Capture checkpoint if requested
        if int(state.current_tick) in checkpoint_set:
            ckpt = capture_checkpoint(
                state,
                checkpoint_id=f"ckpt_tick_{state.current_tick}",
                description=f"Checkpoint at tick {state.current_tick}",
            )
            if output_dir:
                save_checkpoint(
                    ckpt,
                    output_dir / f"checkpoint_tick_{state.current_tick}.json",
                )

        if policy_fn:
            requests = policy_fn(state)
            scheduler.submit_actions(requests, state)

        scheduler.step(state)

    metrics = compute_metrics(state)

    # Flush any missions that never triggered a lifecycle event into the ledger
    ledger = _finalise_ledger(state)

    if output_dir:
        output_dir.mkdir(parents=True, exist_ok=True)
        # Save event log
        save_event_log(state.event_log, output_dir / "events.jsonl")
        # Save metrics
        (output_dir / "metrics.json").write_text(
            json.dumps(asdict(metrics), indent=2), encoding="utf-8"
        )
        # Save mission ledger (state.ledger was populated at runtime; also write it)
        ledger.save(output_dir / "ledger.json")
        # Save state records
        (output_dir / "state_records.json").write_text(
            json.dumps(state.state_records, indent=2), encoding="utf-8"
        )

    return metrics


def _finalise_ledger(state: RuntimeState) -> MissionLedger:
    """
    Ensure every mission in state.missions has an entry in state.ledger.

    Missions that were released and completed in-flight already have entries
    written by MissionManager.  This pass adds any remaining missions that
    never advanced beyond "pending" (e.g. released after max_ticks).
    Returns the in-state ledger for convenience.
    """
    ledger = state.ledger
    for mid, ms in state.missions.items():
        if ledger.get_mission(mid) is not None:
            continue  # already recorded at runtime
        complete_tick = None
        latency = None
        if ms.status == "complete" and ms.completed_at is not None:
            complete_tick = int(ms.completed_at)
            latency = float(ms.completed_at - ms.released_at) if ms.released_at else None
        elif ms.status == "expired" and ms.expired_at is not None:
            complete_tick = int(ms.expired_at)
        elif ms.status == "violated" and ms.violated_at is not None:
            complete_tick = int(ms.violated_at)

        entry = LedgerMissionEntry(
            mission_id=mid,
            family=ms.spec.family.value,
            priority=ms.spec.priority.value,
            release_tick=int(ms.spec.release_tick),
            deadline_tick=int(ms.spec.deadline_tick) if ms.spec.deadline_tick else None,
            status=ms.status,
            complete_tick=complete_tick,
            latency=latency,
            risk_used=ms.risk_used,
        )
        ledger.record_mission(entry)
    return ledger
