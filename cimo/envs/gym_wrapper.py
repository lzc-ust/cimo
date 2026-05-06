"""
Gymnasium-compatible wrapper for CIMO v1.

Wraps CIMOEnv as a gym.Env subclass for use with standard RL libraries.
Requires gymnasium (or gym) to be installed.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

try:
    import gymnasium as gym
    from gymnasium import spaces
    HAS_GYM = True
except ImportError:
    try:
        import gym
        from gym import spaces
        HAS_GYM = True
    except ImportError:
        HAS_GYM = False
        gym = None
        spaces = None

from cimo.core.datatypes import ActionRequest
from cimo.envs.parallel_env import CIMOEnv


if HAS_GYM:
    class CIMOGymEnv(gym.Env):  # type: ignore
        """
        Gymnasium-compatible CIMO environment.

        Observation: flat dict of unit locations, energies, mission statuses.
        Action: list of ActionRequest objects (passed as-is; extend for proper spaces).
        """

        metadata = {"render_modes": []}

        def __init__(
            self,
            scenario_path: Path,
            catalog_dir: Optional[Path] = None,
        ) -> None:
            super().__init__()
            self._env = CIMOEnv(scenario_path, catalog_dir)
            # Placeholder spaces (override for actual RL training)
            self.observation_space = spaces.Dict({})
            self.action_space = spaces.Discrete(1)

        def reset(
            self, *, seed: Optional[int] = None, options: Optional[Dict] = None
        ) -> Tuple[Dict, Dict]:
            obs = self._env.reset()
            return obs, {}

        def step(
            self, action: Any
        ) -> Tuple[Dict, float, bool, bool, Dict]:
            # action expected to be a list of ActionRequests
            if not isinstance(action, list):
                action = []
            obs, reward, done, info = self._env.step(action)
            truncated = False
            return obs, reward, done, truncated, info

        def render(self) -> None:
            pass

        @property
        def state(self):
            return self._env.state

else:
    class CIMOGymEnv:  # type: ignore
        """Stub when gymnasium/gym is not installed."""
        def __init__(self, *args, **kwargs):
            raise ImportError("gymnasium or gym is required for CIMOGymEnv")
