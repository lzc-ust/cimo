#!/usr/bin/env python3
"""
trace_viewer.py - View and summarise CIMO event log (.jsonl) files.

Usage:
    python tools/trace_viewer.py path/to/events.jsonl
    python tools/trace_viewer.py path/to/events.jsonl --filter mission_complete
    python tools/trace_viewer.py path/to/events.jsonl --tick 42
    python tools/trace_viewer.py path/to/events.jsonl --summary
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


def load_events(path: Path) -> list:
    events = []
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                events.append(json.loads(line))
    return events


def print_event(e: dict) -> None:
    tick = e.get("tick", "?")
    etype = e.get("event_type", "unknown")
    actor = e.get("actor_id", "")
    action = e.get("action_id", "")
    mission = e.get("mission_id", "")
    reason = e.get("reason", "")
    payload = e.get("payload", {})
    parts = [f"[tick={tick}]", f"{etype}"]
    if actor:
        parts.append(f"actor={actor}")
    if action:
        parts.append(f"action={action}")
    if mission:
        parts.append(f"mission={mission}")
    if reason:
        parts.append(f"reason={reason}")
    if payload:
        parts.append(f"payload={json.dumps(payload)}")
    print("  ".join(parts))


def print_summary(events: list) -> None:
    counts: dict = {}
    for e in events:
        etype = e.get("event_type", "unknown")
        counts[etype] = counts.get(etype, 0) + 1
    print(f"Total events: {len(events)}")
    print("\nEvent type counts:")
    for etype, count in sorted(counts.items(), key=lambda x: -x[1]):
        print(f"  {etype:40s} {count:6d}")


def main() -> int:
    parser = argparse.ArgumentParser(description="CIMO trace viewer")
    parser.add_argument("file", help="Path to events.jsonl")
    parser.add_argument("--filter", help="Filter by event_type (partial match)")
    parser.add_argument("--tick", type=int, help="Show only events at this tick")
    parser.add_argument("--summary", action="store_true", help="Print summary only")
    args = parser.parse_args()

    path = Path(args.file)
    if not path.exists():
        print(f"File not found: {path}")
        return 1

    events = load_events(path)

    if args.summary:
        print_summary(events)
        return 0

    filtered = events
    if args.tick is not None:
        filtered = [e for e in filtered if e.get("tick") == args.tick]
    if args.filter:
        filtered = [e for e in filtered if args.filter.lower() in e.get("event_type", "").lower()]

    for e in filtered:
        print_event(e)

    print(f"\n({len(filtered)} events shown)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
