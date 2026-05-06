"""
Mission ledger for CIMO v1.

The ledger records the structured outcome of every mission and every
primitive action in chronological order.  It is one of the primary
structured outputs of CIMO-Core.
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional

from cimo.core.ids import ActionId, MissionId, Tick, UnitId


@dataclass
class LedgerActionEntry:
    """One action recorded in the mission ledger."""
    action_id: ActionId
    actor_id: UnitId
    action_type: str
    tick_submitted: int
    tick_started: Optional[int]
    tick_ended: Optional[int]
    outcome: str          # "complete" | "fail" | "reject" | "abort"
    reason: Optional[str]
    energy_consumed: float = 0.0
    distance_travelled: float = 0.0


@dataclass
class LedgerMissionEntry:
    """One mission recorded in the mission ledger."""
    mission_id: MissionId
    family: str
    priority: str
    release_tick: int
    deadline_tick: Optional[int]
    status: str           # "complete" | "violated" | "expired" | "active"
    complete_tick: Optional[int]
    latency: Optional[float]
    risk_used: float
    actions: List[LedgerActionEntry] = field(default_factory=list)


class MissionLedger:
    """
    Structured mission ledger.

    Provides append-only recording of mission and action outcomes,
    and serialisation to JSON.
    """

    def __init__(self) -> None:
        self._missions: Dict[MissionId, LedgerMissionEntry] = {}
        self._standalone_actions: List[LedgerActionEntry] = []

    # ------------------------------------------------------------------
    # Recording
    # ------------------------------------------------------------------

    def record_mission(self, entry: LedgerMissionEntry) -> None:
        self._missions[entry.mission_id] = entry

    def update_mission_status(
        self,
        mission_id: MissionId,
        status: str,
        complete_tick: Optional[int] = None,
        latency: Optional[float] = None,
        risk_used: float = 0.0,
    ) -> None:
        if mission_id in self._missions:
            m = self._missions[mission_id]
            m.status = status
            m.complete_tick = complete_tick
            m.latency = latency
            m.risk_used = risk_used

    def record_action(
        self,
        entry: LedgerActionEntry,
        mission_id: Optional[MissionId] = None,
    ) -> None:
        if mission_id and mission_id in self._missions:
            self._missions[mission_id].actions.append(entry)
        else:
            self._standalone_actions.append(entry)

    # ------------------------------------------------------------------
    # Query
    # ------------------------------------------------------------------

    def get_mission(self, mission_id: MissionId) -> Optional[LedgerMissionEntry]:
        return self._missions.get(mission_id)

    def all_missions(self) -> List[LedgerMissionEntry]:
        return list(self._missions.values())

    def all_actions(self) -> List[LedgerActionEntry]:
        actions: List[LedgerActionEntry] = list(self._standalone_actions)
        for m in self._missions.values():
            actions.extend(m.actions)
        return actions

    # ------------------------------------------------------------------
    # Serialisation
    # ------------------------------------------------------------------

    def to_dict(self) -> Dict[str, Any]:
        return {
            "missions": [asdict(m) for m in self._missions.values()],
            "standalone_actions": [asdict(a) for a in self._standalone_actions],
        }

    def to_json(self, indent: int = 2) -> str:
        return json.dumps(self.to_dict(), indent=indent)

    def save(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(self.to_json(), encoding="utf-8")

    @classmethod
    def load(cls, path: Path) -> "MissionLedger":
        data = json.loads(path.read_text(encoding="utf-8"))
        ledger = cls()
        for m in data.get("missions", []):
            actions = [LedgerActionEntry(**a) for a in m.pop("actions", [])]
            entry = LedgerMissionEntry(**m, actions=actions)
            ledger.record_mission(entry)
        for a in data.get("standalone_actions", []):
            ledger._standalone_actions.append(LedgerActionEntry(**a))
        return ledger
