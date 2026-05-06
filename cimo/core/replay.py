"""
Replay system for CIMO v1.

Replays a completed episode by replaying its event log and state records.
Useful for debugging, visualization, and offline analysis.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, Generator, Iterator, List, Optional


class EventLogReader:
    """
    Reads a JSONL event log file and provides tick-grouped iteration.
    """

    def __init__(self, path: Path) -> None:
        self._path = path
        self._events: List[Dict] = []
        self._load()

    def _load(self) -> None:
        with open(self._path, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line:
                    self._events.append(json.loads(line))

    def all_events(self) -> List[Dict]:
        return list(self._events)

    def events_at_tick(self, tick: int) -> List[Dict]:
        return [e for e in self._events if e.get("tick") == tick]

    def iter_by_tick(self) -> Generator[tuple, None, None]:
        """Yield (tick, [events]) in ascending tick order."""
        ticks: Dict[int, List[Dict]] = {}
        for e in self._events:
            t = e.get("tick", 0)
            ticks.setdefault(t, []).append(e)
        for tick in sorted(ticks):
            yield tick, ticks[tick]

    def filter_by_type(self, event_type: str) -> List[Dict]:
        return [e for e in self._events if e.get("event_type") == event_type]


def save_event_log(events: List[Dict], path: Path) -> None:
    """Save event log as JSON Lines (.jsonl)."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        for event in events:
            f.write(json.dumps(event) + "\n")


def load_event_log(path: Path) -> List[Dict]:
    """Load event log from JSON Lines file."""
    events: List[Dict] = []
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                events.append(json.loads(line))
    return events


class StateRecordReader:
    """
    Reads periodic state records and provides lookup by tick.
    """

    def __init__(self, records: Optional[List[Dict]] = None, path: Optional[Path] = None) -> None:
        self._records: List[Dict] = []
        if records:
            self._records = records
        elif path:
            self._load(path)

    def _load(self, path: Path) -> None:
        with open(path, encoding="utf-8") as f:
            self._records = json.load(f)

    def get_at_tick(self, tick: int) -> Optional[Dict]:
        """Return the state record at or before the given tick."""
        best = None
        for r in self._records:
            if r.get("tick", 0) <= tick:
                best = r
            else:
                break
        return best

    def all_records(self) -> List[Dict]:
        return list(self._records)


def replay_summary(event_log: List[Dict]) -> Dict[str, Any]:
    """
    Produce a summary of an episode from its event log.

    Returns counts of key event types.
    """
    summary: Dict[str, Any] = {}
    for event in event_log:
        etype = event.get("event_type", "unknown")
        summary[etype] = summary.get(etype, 0) + 1
    summary["total_events"] = len(event_log)
    return summary
