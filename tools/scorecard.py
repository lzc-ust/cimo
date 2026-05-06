#!/usr/bin/env python3
"""
scorecard.py - Compute and display the CIMO benchmark scorecard.

Usage:
    python tools/scorecard.py path/to/metrics.json
    python tools/scorecard.py --dir path/to/results/   # aggregate multiple runs
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


def load_metrics(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def _nested(metrics: dict, *keys, default=None):
    """Safe nested key lookup."""
    obj = metrics
    for k in keys:
        if not isinstance(obj, dict):
            return default
        obj = obj.get(k, default)
    return obj


def print_scorecard(metrics: dict, label: str = "") -> None:
    """Print a structured scorecard in 5 indicator groups."""
    sep = "─" * 60
    if label:
        print(f"\n{'═' * 60}")
        print(f"  {label}")
        print(f"{'═' * 60}")

    print(f"  Scenario ID  : {metrics.get('scenario_id', 'N/A')}")
    print(f"  Total ticks  : {metrics.get('total_ticks', 0)}")

    # Try to read from nested groups, fall back to flat fields
    tc = metrics.get("task_completion") or {}
    ef = metrics.get("efficiency") or {}
    cc = metrics.get("coverage_connectivity") or {}
    rk = metrics.get("risk") or {}
    cmp = metrics.get("composite") or {}

    # --- Group 1: Task Completion ---
    print(f"\n  {sep}")
    print(f"  Group 1 · Task Completion (§8.1)")
    print(f"  {sep}")
    total = tc.get("missions_total") or (
        (metrics.get("missions_completed", 0) or 0)
        + (metrics.get("missions_violated", 0) or 0)
        + (metrics.get("missions_expired", 0) or 0)
    )
    completed = tc.get("missions_completed", metrics.get("missions_completed", 0))
    violated  = tc.get("missions_violated",  metrics.get("missions_violated",  0))
    expired   = tc.get("missions_expired",   metrics.get("missions_expired",   0))
    comp_rate = tc.get("completion_rate", completed / total if total else 0.0)
    viol_rate = tc.get("violation_rate",  violated  / total if total else 0.0)
    latency   = tc.get("mean_mission_latency", metrics.get("mean_mission_latency", 0.0))
    print(f"    Missions total     : {total}")
    print(f"    Completed          : {completed}  ({comp_rate:.1%})")
    print(f"    Violated           : {violated}   ({viol_rate:.1%})")
    print(f"    Expired            : {expired}")
    print(f"    Mean latency       : {latency:.1f} ticks")

    # Per-mission detail
    pm = tc.get("per_mission") or metrics.get("per_mission_metrics") or {}
    if pm:
        print(f"    Per-mission:")
        for mid, md in sorted(pm.items()):
            lat_str = f"{md.get('latency'):.1f}" if md.get("latency") is not None else "—"
            print(f"      {mid:<30} {md.get('status','?'):<10} latency={lat_str}  risk={md.get('risk_used', 0.0):.3f}")

    # --- Group 2: Efficiency ---
    print(f"\n  {sep}")
    print(f"  Group 2 · Efficiency (§8.2)")
    print(f"  {sep}")
    energy   = ef.get("total_energy_consumed",   metrics.get("total_energy_consumed",   0.0))
    distance = ef.get("total_distance_travelled", metrics.get("total_distance_travelled", 0.0))
    print(f"    Total energy used  : {energy:.2f}")
    print(f"    Total distance     : {distance:.2f} m")
    pu = ef.get("per_unit") or metrics.get("per_unit_metrics") or {}
    if pu:
        print(f"    Per-unit:")
        for uid, ud in sorted(pu.items()):
            print(f"      {uid:<25} E={ud.get('energy_consumed', 0.0):.2f}  D={ud.get('distance_travelled', 0.0):.2f}  loc={ud.get('location', '?')}")

    # --- Group 3: Coverage & Connectivity ---
    print(f"\n  {sep}")
    print(f"  Group 3 · Coverage & Connectivity (§8.3)")
    print(f"  {sep}")
    cov_frac   = cc.get("coverage_fraction",          metrics.get("coverage_fraction",          0.0))
    relay_frac = cc.get("relay_connectivity_fraction", metrics.get("relay_connectivity_fraction", 0.0))
    print(f"    Coverage fraction  : {cov_frac:.2%}")
    print(f"    Relay connectivity : {relay_frac:.2%}")

    # --- Group 4: Risk ---
    print(f"\n  {sep}")
    print(f"  Group 4 · Risk (§8.4)")
    print(f"  {sep}")
    total_risk = rk.get("total_risk_accumulated", metrics.get("total_risk_accumulated", 0.0))
    print(f"    Total risk         : {total_risk:.4f}")
    pur = rk.get("per_unit") or {}
    if pur:
        print(f"    Per-unit risk:")
        for uid, rv in sorted(pur.items()):
            print(f"      {uid:<25} {rv:.4f}")

    # --- Group 5: Composite Score ---
    print(f"\n  {sep}")
    print(f"  Group 5 · Composite Score (§8.5)")
    print(f"  {sep}")
    score    = cmp.get("score", 0.0)
    weights  = cmp.get("weights") or {}
    comps    = cmp.get("components") or {}
    print(f"    Score              : {score:.4f}  ({score:.1%})")
    if weights and comps:
        print(f"    Components:")
        for k, w in sorted(weights.items(), key=lambda x: -x[1]):
            v = comps.get(k, 0.0)
            print(f"      {k:<35} value={v:.3f}  weight={w:.2f}  contrib={v*w:.4f}")


def aggregate_scorecards(metrics_list: list) -> dict:
    """Average numeric fields across multiple metric dicts."""
    if not metrics_list:
        return {}
    keys = [
        "total_ticks", "missions_completed", "missions_violated", "missions_expired",
        "total_energy_consumed", "total_distance_travelled", "total_risk_accumulated",
        "mean_mission_latency", "coverage_fraction", "relay_connectivity_fraction",
    ]
    agg: dict = {"scenario_id": "AGGREGATE", "n_runs": len(metrics_list)}
    for k in keys:
        vals = [m.get(k, 0) for m in metrics_list]
        agg[k] = sum(vals) / len(vals)
    return agg


def main() -> int:
    parser = argparse.ArgumentParser(description="CIMO benchmark scorecard")
    parser.add_argument("files", nargs="*", help="metrics.json files")
    parser.add_argument("--dir", help="Directory containing metrics.json files")
    args = parser.parse_args()

    paths: list[Path] = []
    if args.dir:
        paths.extend(Path(args.dir).rglob("metrics.json"))
    for f in args.files:
        paths.append(Path(f))

    if not paths:
        print("No files specified.")
        return 1

    all_metrics = []
    for p in paths:
        if not p.exists():
            print(f"File not found: {p}")
            continue
        m = load_metrics(p)
        print_scorecard(m, label=str(p))
        all_metrics.append(m)

    if len(all_metrics) > 1:
        agg = aggregate_scorecards(all_metrics)
        print_scorecard(agg, label=f"AGGREGATE ({len(all_metrics)} runs)")

    return 0


if __name__ == "__main__":
    sys.exit(main())
