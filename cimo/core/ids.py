"""
ID type definitions for CIMO v1.
All identifiers are typed strings to enable static analysis and validation.
"""

from typing import NewType

# ---------------------------------------------------------------------------
# Typed identifiers
# ---------------------------------------------------------------------------

#: Unique identifier for a node in the metric graph (location).
NodeId = NewType("NodeId", str)

#: Unique identifier for an edge in the metric graph.
EdgeId = NewType("EdgeId", str)

#: Unique identifier for a unit instance in a scenario.
UnitId = NewType("UnitId", str)

#: Unique identifier for an object instance in a scenario.
ObjectId = NewType("ObjectId", str)

#: Unique identifier for a target in a scenario.
TargetId = NewType("TargetId", str)

#: Unique identifier for a mission in a scenario.
MissionId = NewType("MissionId", str)

#: Unique identifier for a disturbance definition.
DisturbanceId = NewType("DisturbanceId", str)

#: Unique identifier for an action request.
ActionId = NewType("ActionId", str)

#: Unique identifier for a scenario.
ScenarioId = NewType("ScenarioId", str)

#: Unique identifier for a checkpoint.
CheckpointId = NewType("CheckpointId", str)

#: Integer tick timestamp.
Tick = NewType("Tick", int)
