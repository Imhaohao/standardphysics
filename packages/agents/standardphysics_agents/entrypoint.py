"""The one call Lane D's API makes on every pass and every furniture drag.

`assess` returns the whole pass, including what it could not answer and the
fingerprint of the layout it judged. The API wants the findings and nothing
else, fast enough to run while somebody is still holding a table, so that is
what this hands back.

The provider is built once and kept. It caches the occupancy grid per layout,
so re-checking the same shop after a drag rebuilds the grid once rather than
once per check.
"""

from __future__ import annotations

from functools import lru_cache

from standardphysics_contracts import Finding, MeasurementProvider, Scenario, SceneGraph
from standardphysics_contracts.rules import Tier

from .assess import assess
from .rules import load_pack
from .tracing import traced

RULEPACK_VERSION: str = load_pack().version


@lru_cache(maxsize=1)
def default_measurements() -> MeasurementProvider:
    from standardphysics_pipeline import PipelineMeasurements

    return PipelineMeasurements()


@traced("findings_for")
def findings_for(
    graph: SceneGraph,
    scenario: Scenario,
    measure: MeasurementProvider | None = None,
    max_tier: Tier = 1,
) -> list[Finding]:
    """Problems first, then requests, then what passed."""
    return assess(
        graph, scenario, measure or default_measurements(), max_tier=max_tier
    ).findings
