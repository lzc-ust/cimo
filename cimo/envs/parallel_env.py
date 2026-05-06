"""
Parallel environment for CIMO v1.

Supports running multiple independent CIMO episodes concurrently
(e.g. for vectorised RL training).

Each environment slot maintains its own RuntimeState and Scheduler.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple

from cimo.core.datatypes import ActionRequest, MetricBundle
from cimo.core.metrics import compute_metrics
from cimo.core.scheduler import Scheduler
from cimo.core.state import RuntimeState
from cimo.sdl.compiler import compile_scenario_file


class CIMOEnv:
    """
    Single CIMO episode environment.

    Interface:
        env.reset() -> obs
        obs, reward, done, info = env.step(action_requests)
    """

    def __init__(
        self,
        scenario_path: Path,
        catalog_dir: Optional[Path] = None,
        reward_fn: Optional[Callable[["CIMOEnv"], float]] = None,
    ) -> None:
        self._scenario_path = scenario_path
        self._catalog_dir = catalog_dir
        self._reward_fn = reward_fn or _default_reward
        self._state: Optional[RuntimeState] = None
        self._scheduler: Optional[Scheduler] = None

    def reset(self) -> Dict[str, Any]:
        """Reset the environment and return the initial observation."""
        self._state = compile_scenario_file(self._scenario_path, self._catalog_dir)
        self._scheduler = Scheduler()
        return self._observe()

    def step(
        self,
        action_requests: List[ActionRequest],
    ) -> Tuple[Dict[str, Any], float, bool, Dict]:
        """
        Submit action requests and advance by one tick.

        Returns:
            obs: observation dict
            reward: scalar reward
            done: episode done flag
            info: auxiliary info dict
        """
        assert self._state is not None, "Call reset() before step()"
        self._scheduler.submit_actions(action_requests, self._state)
        self._scheduler.step(self._state)
        obs = self._observe()
        reward = self._reward_fn(self)
        done = self._state.episode_done
        info = {
            "tick": int(self._state.current_tick),
            "missions_completed": self._state.missions_completed,
            "missions_violated": self._state.missions_violated,
        }
        return obs, reward, done, info

    def compute_metrics(self) -> MetricBundle:
        """Compute and return the MetricBundle for the current/completed episode."""
        assert self._state is not None
        return compute_metrics(self._state)

    @property
    def state(self) -> Optional[RuntimeState]:
        return self._state

    def _observe(self) -> Dict[str, Any]:
        """Build a structured observation from the current RuntimeState."""
        s = self._state
        return {
            "tick": int(s.current_tick),
            "units": {
                uid: {
                    "location": u.location,
                    "energy": u.energy,
                    "busy": s.is_unit_busy(uid),
                    "team_mode": u.team_mode.value if u.team_mode else None,
                }
                for uid, u in s.units.items()
            },
            "objects": {
                oid: {
                    "location": o.location,
                    "carried_by": o.carried_by,
                }
                for oid, o in s.objects.items()
            },
            "missions": {
                mid: ms.status
                for mid, ms in s.missions.items()
            },
            "targets": {
                tid: {
                    "assessment_state": t.assessment_state,
                    "access_operable": t.access_operable,
                    "service_progress": t.service_progress,
                    "coverage_active": t.coverage_active,
                }
                for tid, t in s.targets.items()
            },
        }


def _default_reward(env: "CIMOEnv") -> float:
    """Default reward: +1 for each mission completed this tick, -0.01 per tick."""
    s = env.state
    if s is None:
        return 0.0
    # Check last event for mission_complete
    reward = -0.01
    for event in reversed(s.event_log):
        if event.get("tick") == int(s.current_tick) - 1:
            if event.get("event_type") == "mission_complete":
                reward += 1.0
        elif event.get("tick", 0) < int(s.current_tick) - 1:
            break
    return reward


class ParallelCIMOEnv:
    """
    Vectorised wrapper running N independent CIMOEnv instances.
    """

    def __init__(
        self,
        scenario_paths: List[Path],
        catalog_dir: Optional[Path] = None,
    ) -> None:
        self._envs = [
            CIMOEnv(p, catalog_dir) for p in scenario_paths
        ]

    def reset(self) -> List[Dict[str, Any]]:
        return [env.reset() for env in self._envs]

    def step(
        self,
        actions_per_env: List[List[ActionRequest]],
    ) -> List[Tuple[Dict, float, bool, Dict]]:
        return [
            env.step(acts)
            for env, acts in zip(self._envs, actions_per_env)
        ]

    def __len__(self) -> int:
        return len(self._envs)
