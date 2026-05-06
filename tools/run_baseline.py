#!/usr/bin/env python3
"""
run_baseline.py — CIMO v1 全量 Baseline 评测脚本

针对所有场景运行贪心策略 (greedy_policy)，
输出每个场景的 metrics.json / ledger.json，
最终汇总为 aggregate_scorecard.json 并打印 5 族 Scorecard。

用法:
    cd e:/cimo_project
    python tools/run_baseline.py                          # 跑全部场景
    python tools/run_baseline.py --suite CIMO-Core        # 只跑指定套件
    python tools/run_baseline.py --scenario campus_transfer_train_001  # 跑单个场景
    python tools/run_baseline.py --output-dir results/baseline_run1

输出目录结构:
    <output_dir>/
        <scenario_id>/
            metrics.json
            ledger.json
            events.jsonl
            state_records.json
        aggregate_scorecard.json
        summary.txt
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from dataclasses import asdict
from pathlib import Path
from typing import Dict, List, Optional

# ── Ensure project root is on PYTHONPATH ──────────────────────────────────────
_ROOT = Path(__file__).resolve().parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from cimo.envs.offline_runner import run_offline
from tools.scorecard import aggregate_scorecards, print_scorecard

# ---------------------------------------------------------------------------
# greedy_policy (inline copy from visualizer so this script is self-contained)
# ---------------------------------------------------------------------------
from typing import List as _List

from cimo.core.datatypes import ActionRequest
from cimo.core.enums import ActionType, TeamMode
from cimo.core.ids import ActionId
from cimo.core.state import RuntimeState


def _next_hop(state: RuntimeState, unit_id: str, dest: str) -> Optional[str]:
    """BFS next hop from unit_id's location toward dest."""
    from collections import deque
    start = state.units[unit_id].location
    if start == dest:
        return None
    blocked_edges = {
        eid
        for ds in state.disturbances.values()
        if ds.is_active and ds.spec.effect == "block"
        for eid in ds.spec.affected_edges
    }
    graph = state.graph
    queue: deque = deque([(start, [start])])
    visited = {start}
    while queue:
        node, path = queue.popleft()
        for edge in graph.outgoing_edges(node):  # MetricGraph API: outgoing_edges()
            if edge.edge_id in blocked_edges:
                continue
            nxt = edge.target
            if nxt in visited:
                continue
            new_path = path + [nxt]
            if nxt == dest:
                return new_path[1] if len(new_path) > 1 else None
            visited.add(nxt)
            queue.append((nxt, new_path))
    return None


def _find_unit_active_mission(state: RuntimeState, unit_id: str) -> Optional[str]:
    """Return the first active mission that lists unit_id in assigned_units."""
    for mid, ms in state.missions.items():
        if ms.status == "active" and unit_id in ms.spec.assigned_units:
            return mid
    return None


def _get_team_mode(mode_str: str) -> TeamMode:
    try:
        return TeamMode(mode_str)
    except ValueError:
        return TeamMode.airlift


def greedy_policy(state: RuntimeState) -> _List[ActionRequest]:
    """
    Greedy baseline policy.

    Rules:
    - Each idle unit looks for its assigned active mission.
    - relocate_object : pick object, traverse to dest, drop.
    - relocate_unit   : actor attaches to passenger, traverses to dest, detaches.
    - assess_target   : traverse to target location, inspect.
    - maintain_coverage: each relay moves to an uncovered coverage target.
    - enable_access / restore_service: traverse to target, repair.
    - recover_unit    : traverse to target_unit's location, then tow to dest.
    """
    requests: _List[ActionRequest] = []
    _counter = [0]

    def nxt_id() -> ActionId:
        _counter[0] += 1
        return ActionId(f"auto_{state.current_tick}_{_counter[0]}")

    for uid, unit in state.units.items():
        if state.is_unit_busy(uid) or not unit.is_active:
            continue

        task = _find_unit_active_mission(state, uid)
        if task is None:
            continue

        ms = state.missions[task]
        family = ms.spec.family.value
        params = ms.spec.params

        # ── relocate_object ────────────────────────────────────────────────
        if family == "relocate_object":
            obj_id = params.get("object_id")
            dest = params.get("destination_node") or params.get("destination")
            if not obj_id or not dest:
                continue
            obj = state.objects.get(obj_id)
            if obj is None:
                continue
            if obj.carried_by == uid:
                if unit.location != dest:
                    hop = _next_hop(state, uid, dest)
                    if hop:
                        requests.append(ActionRequest(
                            action_id=nxt_id(), action_type=ActionType.traverse,
                            actor_id=uid, tick_submitted=state.current_tick,
                            target_node=hop))
                else:
                    requests.append(ActionRequest(
                        action_id=nxt_id(), action_type=ActionType.drop,
                        actor_id=uid, tick_submitted=state.current_tick,
                        object_id=obj_id))
            elif obj.location == unit.location:
                requests.append(ActionRequest(
                    action_id=nxt_id(), action_type=ActionType.pick,
                    actor_id=uid, tick_submitted=state.current_tick,
                    object_id=obj_id))
            else:
                hop = _next_hop(state, uid, obj.location or dest)
                if hop:
                    requests.append(ActionRequest(
                        action_id=nxt_id(), action_type=ActionType.traverse,
                        actor_id=uid, tick_submitted=state.current_tick,
                        target_node=hop))

        # ── relocate_unit ──────────────────────────────────────────────────
        elif family == "relocate_unit":
            dest = params.get("destination_node") or params.get("destination")
            target_uid = params.get("unit_id")
            if not dest or not target_uid:
                continue
            target_unit = state.units.get(target_uid)
            if target_unit is None:
                continue
            if uid == target_uid:
                pass  # passenger; handled by actor
            else:
                if unit.team_partner is None:
                    if unit.location == target_unit.location:
                        requests.append(ActionRequest(
                            action_id=nxt_id(), action_type=ActionType.attach,
                            actor_id=uid, tick_submitted=state.current_tick,
                            passenger_id=target_uid,
                            team_mode=_get_team_mode(params.get("team_mode", "airlift"))))
                    else:
                        hop = _next_hop(state, uid, target_unit.location)
                        if hop:
                            requests.append(ActionRequest(
                                action_id=nxt_id(), action_type=ActionType.traverse,
                                actor_id=uid, tick_submitted=state.current_tick,
                                target_node=hop))
                else:
                    if unit.location != dest:
                        hop = _next_hop(state, uid, dest)
                        if hop:
                            requests.append(ActionRequest(
                                action_id=nxt_id(), action_type=ActionType.traverse,
                                actor_id=uid, tick_submitted=state.current_tick,
                                target_node=hop))
                    else:
                        requests.append(ActionRequest(
                            action_id=nxt_id(), action_type=ActionType.detach,
                            actor_id=uid, tick_submitted=state.current_tick))

        # ── assess_target ──────────────────────────────────────────────────
        elif family == "assess_target":
            target_id = params.get("target_id")
            if not target_id:
                continue
            target = state.targets.get(target_id)
            if target is None:
                continue
            if unit.location == target.location:
                mode_str = params.get("assessment_mode", "inspect")
                from cimo.core.enums import AssessmentMode
                try:
                    amode = AssessmentMode(mode_str)
                except ValueError:
                    amode = AssessmentMode.inspect
                requests.append(ActionRequest(
                    action_id=nxt_id(), action_type=ActionType.inspect,
                    actor_id=uid, tick_submitted=state.current_tick,
                    target_id=target_id, assessment_mode=amode))
            else:
                hop = _next_hop(state, uid, target.location)
                if hop:
                    requests.append(ActionRequest(
                        action_id=nxt_id(), action_type=ActionType.traverse,
                        actor_id=uid, tick_submitted=state.current_tick,
                        target_node=hop))

        # ── enable_access ──────────────────────────────────────────────────
        elif family == "enable_access":
            target_id = params.get("target_id")
            if not target_id:
                continue
            target = state.targets.get(target_id)
            if target is None:
                continue
            if unit.location == target.location:
                requests.append(ActionRequest(
                    action_id=nxt_id(), action_type=ActionType.clear_blockage,
                    actor_id=uid, tick_submitted=state.current_tick,
                    target_id=target_id))
            else:
                hop = _next_hop(state, uid, target.location)
                if hop:
                    requests.append(ActionRequest(
                        action_id=nxt_id(), action_type=ActionType.traverse,
                        actor_id=uid, tick_submitted=state.current_tick,
                        target_node=hop))

        # ── restore_service ────────────────────────────────────────────────
        elif family == "restore_service":
            target_id = params.get("target_id")
            if not target_id:
                continue
            target = state.targets.get(target_id)
            if target is None:
                continue
            if unit.location == target.location:
                requests.append(ActionRequest(
                    action_id=nxt_id(), action_type=ActionType.repair,
                    actor_id=uid, tick_submitted=state.current_tick,
                    target_id=target_id))
            else:
                hop = _next_hop(state, uid, target.location)
                if hop:
                    requests.append(ActionRequest(
                        action_id=nxt_id(), action_type=ActionType.traverse,
                        actor_id=uid, tick_submitted=state.current_tick,
                        target_node=hop))

        # ── maintain_coverage ──────────────────────────────────────────────
        elif family == "maintain_coverage":
            target_ids = params.get("target_ids", [])
            # Find uncovered target, move toward it
            uncovered = [
                tid for tid in target_ids
                if tid in state.targets and not state.targets[tid].coverage_active
            ]
            if not uncovered:
                # All covered; stay put (monitor)
                requests.append(ActionRequest(
                    action_id=nxt_id(), action_type=ActionType.monitor,
                    actor_id=uid, tick_submitted=state.current_tick))
            else:
                # Pick the first uncovered target not already targeted by another unit
                active_dests = {
                    state.active_actions[a].params.get("target_node")
                    for a in state.active_actions
                    if a != uid
                }
                dest_tid = next(
                    (t for t in uncovered
                     if state.targets[t].location not in active_dests),
                    uncovered[0]
                )
                dest_node = state.targets[dest_tid].location
                if unit.location == dest_node:
                    requests.append(ActionRequest(
                        action_id=nxt_id(), action_type=ActionType.monitor,
                        actor_id=uid, tick_submitted=state.current_tick))
                else:
                    hop = _next_hop(state, uid, dest_node)
                    if hop:
                        requests.append(ActionRequest(
                            action_id=nxt_id(), action_type=ActionType.traverse,
                            actor_id=uid, tick_submitted=state.current_tick,
                            target_node=hop))

        # ── recover_unit ───────────────────────────────────────────────────
        elif family == "recover_unit":
            target_uid2 = params.get("target_unit_id")
            dest = params.get("destination") or params.get("destination_node")
            if not target_uid2 or not dest:
                continue
            target_unit2 = state.units.get(target_uid2)
            if target_unit2 is None:
                continue
            if uid == target_uid2:
                pass
            else:
                if unit.team_partner is None:
                    if unit.location == target_unit2.location:
                        requests.append(ActionRequest(
                            action_id=nxt_id(), action_type=ActionType.attach,
                            actor_id=uid, tick_submitted=state.current_tick,
                            passenger_id=target_uid2,
                            team_mode=TeamMode.tow))
                    else:
                        hop = _next_hop(state, uid, target_unit2.location)
                        if hop:
                            requests.append(ActionRequest(
                                action_id=nxt_id(), action_type=ActionType.traverse,
                                actor_id=uid, tick_submitted=state.current_tick,
                                target_node=hop))
                else:
                    if unit.location != dest:
                        hop = _next_hop(state, uid, dest)
                        if hop:
                            requests.append(ActionRequest(
                                action_id=nxt_id(), action_type=ActionType.traverse,
                                actor_id=uid, tick_submitted=state.current_tick,
                                target_node=hop))
                    else:
                        requests.append(ActionRequest(
                            action_id=nxt_id(), action_type=ActionType.detach,
                            actor_id=uid, tick_submitted=state.current_tick))

    return requests


# ---------------------------------------------------------------------------
# Scenario discovery
# ---------------------------------------------------------------------------

SCENARIOS_DIR = _ROOT / "cimo" / "specs" / "scenarios"
CATALOGS_DIR  = _ROOT / "cimo" / "specs" / "catalogs"

# Map suite name → scenario file prefixes (by YAML meta.suite field)
SUITE_FILTER_MAP: Dict[str, str] = {
    "CIMO-Core":  "campus_transfer_train",
    "CIMO-Dyn":   "crossing_team_train",
    "CIMO-Pref":  "maintain_coverage",
    "CIMO-Shift": "crossing_team_shift",
}


def discover_scenarios(
    suite: Optional[str] = None,
    scenario_id: Optional[str] = None,
) -> List[Path]:
    """Return list of scenario YAML paths matching the filter."""
    all_yamls = sorted(SCENARIOS_DIR.glob("*.yaml"))
    if scenario_id:
        return [p for p in all_yamls if p.stem == scenario_id]
    if suite:
        # Filter by reading the meta.suite field from each YAML
        import yaml  # type: ignore
        result = []
        for p in all_yamls:
            try:
                raw = yaml.safe_load(p.read_text(encoding="utf-8"))
                if isinstance(raw, dict) and raw.get("meta", {}).get("suite") == suite:
                    result.append(p)
            except Exception:
                pass
        return result
    return all_yamls


# ---------------------------------------------------------------------------
# Aggregate scorecard
# ---------------------------------------------------------------------------

def build_aggregate(results: List[Dict]) -> Dict:
    """
    Aggregate numeric fields across multiple metric dicts.
    Groups results by suite when possible.
    """
    if not results:
        return {}

    flat_keys = [
        "total_ticks", "missions_completed", "missions_violated", "missions_expired",
        "total_energy_consumed", "total_distance_travelled", "total_risk_accumulated",
        "mean_mission_latency", "coverage_fraction", "relay_connectivity_fraction",
    ]
    agg: Dict = {
        "scenario_id": "AGGREGATE",
        "n_scenarios": len(results),
    }
    for k in flat_keys:
        vals = [r.get(k, 0) or 0 for r in results]
        agg[k] = sum(vals) / len(vals)

    # Aggregate group 1: task_completion
    tc_vals = [r.get("task_completion") or {} for r in results]
    agg["task_completion"] = {
        "missions_total":        sum(v.get("missions_total", 0) for v in tc_vals),
        "missions_completed":    sum(v.get("missions_completed", 0) for v in tc_vals),
        "missions_violated":     sum(v.get("missions_violated", 0) for v in tc_vals),
        "missions_expired":      sum(v.get("missions_expired", 0) for v in tc_vals),
        "completion_rate":       _safe_avg([v.get("completion_rate", 0) for v in tc_vals]),
        "violation_rate":        _safe_avg([v.get("violation_rate", 0) for v in tc_vals]),
        "mean_mission_latency":  _safe_avg([v.get("mean_mission_latency", 0) for v in tc_vals]),
    }
    # Group 2
    ef_vals = [r.get("efficiency") or {} for r in results]
    agg["efficiency"] = {
        "total_energy_consumed":   sum(v.get("total_energy_consumed", 0) for v in ef_vals),
        "total_distance_travelled": sum(v.get("total_distance_travelled", 0) for v in ef_vals),
    }
    # Group 3
    cc_vals = [r.get("coverage_connectivity") or {} for r in results]
    agg["coverage_connectivity"] = {
        "coverage_fraction":           _safe_avg([v.get("coverage_fraction", 0) for v in cc_vals]),
        "relay_connectivity_fraction": _safe_avg([v.get("relay_connectivity_fraction", 0) for v in cc_vals]),
    }
    # Group 4
    rk_vals = [r.get("risk") or {} for r in results]
    agg["risk"] = {
        "total_risk_accumulated": sum(v.get("total_risk_accumulated", 0) for v in rk_vals),
    }
    # Group 5
    cmp_vals = [r.get("composite") or {} for r in results]
    agg["composite"] = {
        "score": _safe_avg([v.get("score", 0) for v in cmp_vals]),
        "weights": cmp_vals[0].get("weights", {}) if cmp_vals else {},
        "components": {
            k: _safe_avg([v.get("components", {}).get(k, 0) for v in cmp_vals])
            for k in (cmp_vals[0].get("components", {}) if cmp_vals else {})
        },
    }
    return agg


def _safe_avg(vals: List) -> float:
    filtered = [v for v in vals if v is not None]
    return sum(filtered) / len(filtered) if filtered else 0.0


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> int:
    parser = argparse.ArgumentParser(
        description="CIMO v1 Baseline Evaluation — runs greedy policy on all scenarios"
    )
    parser.add_argument("--suite",     help="Filter by suite name (e.g. CIMO-Core)")
    parser.add_argument("--scenario",  help="Run a single scenario by ID (stem of YAML file)")
    parser.add_argument("--output-dir", default="results/baseline",
                        help="Root output directory (default: results/baseline)")
    parser.add_argument("--no-save",   action="store_true",
                        help="Skip saving per-scenario output files")
    parser.add_argument("--quiet",     action="store_true",
                        help="Only print aggregate scorecard")
    args = parser.parse_args()

    output_root = Path(args.output_dir).resolve()
    scenarios = discover_scenarios(suite=args.suite, scenario_id=args.scenario)

    if not scenarios:
        print(f"[baseline] No scenarios found (suite={args.suite!r}, scenario={args.scenario!r})")
        return 1

    print(f"\n[baseline] Running greedy policy on {len(scenarios)} scenario(s)...")
    print(f"[baseline] Output dir: {output_root}\n")

    all_results: List[Dict] = []
    errors: List[str] = []
    t0 = time.perf_counter()

    for scenario_path in scenarios:
        sid = scenario_path.stem
        out_dir = (output_root / sid) if not args.no_save else None
        t_s = time.perf_counter()
        try:
            metrics = run_offline(
                scenario_path=scenario_path,
                policy_fn=greedy_policy,
                output_dir=out_dir,
                catalog_dir=CATALOGS_DIR,
            )
            elapsed = time.perf_counter() - t_s
            m_dict = asdict(metrics)
            all_results.append(m_dict)

            if not args.quiet:
                print_scorecard(m_dict, label=f"{sid}  ({elapsed:.1f}s)")

        except Exception as exc:
            elapsed = time.perf_counter() - t_s
            msg = f"[ERROR] {sid}: {exc}"
            errors.append(msg)
            print(msg)

    elapsed_total = time.perf_counter() - t0
    print(f"\n[baseline] Finished {len(all_results)}/{len(scenarios)} scenarios in {elapsed_total:.1f}s")
    if errors:
        print(f"[baseline] {len(errors)} scenario(s) failed:")
        for e in errors:
            print(f"  {e}")

    # Aggregate scorecard
    if all_results:
        agg = build_aggregate(all_results)
        print_scorecard(agg, label=f"AGGREGATE  ({len(all_results)} scenarios)")

        if not args.no_save:
            output_root.mkdir(parents=True, exist_ok=True)
            agg_path = output_root / "aggregate_scorecard.json"
            agg_path.write_text(json.dumps(agg, indent=2), encoding="utf-8")

            # Per-scenario index
            index = [
                {
                    "scenario_id": r.get("scenario_id"),
                    "total_ticks": r.get("total_ticks"),
                    "composite_score": (r.get("composite") or {}).get("score", r.get("missions_completed", 0)),
                    "completion_rate": (r.get("task_completion") or {}).get("completion_rate",
                                        r.get("missions_completed", 0)),
                }
                for r in all_results
            ]
            index.sort(key=lambda x: x.get("composite_score", 0), reverse=True)
            (output_root / "summary.json").write_text(
                json.dumps(index, indent=2), encoding="utf-8"
            )
            print(f"\n[baseline] Aggregate scorecard saved to: {agg_path}")

    return 0 if not errors else 2


if __name__ == "__main__":
    sys.exit(main())
