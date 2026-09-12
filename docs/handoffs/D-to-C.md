# D to C: contract changes, the fixture scenario, and where checks plug in

## Contract changes landing next

All are additive. JSON that validates today still validates.

| Change | What it is for |
|---|---|
| `Stop.anchor_node_id: UUID \| None = None` | The fixture a stop is at, so route width ignores only that object near the stop (audit A-6) |
| `WidthResult.needs_measurement: bool = False` | Set by `door_clear_width`, because a scan cannot see the door open 90 degrees. Turn it into a question with a photo request, not a pass (audit A-9) |
| `graph_hash(graph)` | The one hash for `Assessment.graph_hash` and `Proposal.base_graph_hash` |

## The fixture scenario

The Seat stop moves out of table_3, where it sat at the table's centre, and
every stop gains an anchor. Leg 0 keeps its 31 in pinch. Legs 2 and 3 change,
so do not pin their current numbers in tests.

## Where your checks plug in

The API runs every stage a real scan goes through: ingest, label, geometry,
scenario, assess, render. Assess is a single function in
`services/api/standardphysics_api/stages.py`, and your entrypoint replaces it.

Until you have an entrypoint, an interim version runs Lane B's real
measurements for two checks: route width against ADA 2010 403.5.1 and counter
height against 904.4.1. It covers only the sample shop, because no real scan
has stops yet. Its findings let me build the viewer callouts and drag
re-checking against real-shaped data. It is not a rule pack, and your checks
replace it outright.

What would help most is your entrypoint's name and signature. My proposal:

```python
def assess(graph: SceneGraph, scenario: Scenario) -> list[Finding]: ...
RULEPACK_VERSION: str
```

It should stay fast enough to call on every furniture drag, which means under a
second on a shop. The router, Weave and the fix agent can sit behind a separate
call.

## A question for you and B

Who places the stops on a real scan? Route checks need an Entrance, Counter,
Pickup, Seat and Exit, and RoomPlan gives us none of them. The API stores one
scenario per scan and the viewer draws it, whoever ends up producing it.
