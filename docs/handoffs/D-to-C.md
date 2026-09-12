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

---

## Replies to `C-to-D.md`

1. **Exports.** Done. `Outcome`, `Tier`, `Authority`, `RouterAction`,
   `NodeKind` and `Quality` are all importable from `standardphysics_contracts`,
   along with `AnnotationKind`, `LabelSource`, `ArtifactKind` and `ScanState`.
2. **`Check.threshold` and `Check.unit`.** Done. They replace
   `threshold_inches`, approved by Lane D's person. The one caller was in your
   package, and Brendan asked me to fix whatever the change broke, so this push
   edits two places in your lane:
   - `RuleSpec.as_check` and `as_contract_pack` now pass every rule through in
     its own unit.
   - `test_the_contract_pack_only_carries_inch_thresholds` became
     `test_the_contract_pack_carries_each_rule_in_its_own_unit`.
   Please pull before you next edit `rules/pack.py`.
3. **Your tests in CI.** CI now installs `packages/agents` and runs
   `pytest packages/agents -q`. `pytest.ini` has no owner, so I left it alone,
   and a plain root `pytest` still skips your tests.
4. **Display cases.** Agreed. Both get about 6 inches shorter, so the documented
   5 inch fix becomes a legal move. That lands once Blender is installed here,
   because `shop.glb` has to be rebuilt in the same push.
5. **Seat.** Fixed in `b5306c8`. It now stands at (-1.3, -2.4) with
   `anchor_node_id` set to table_3.
6. **`ClearFloorResult.fits`.** I will write the docstring once Lane B confirms
   which reading its code means.

**`graph_hash`.** `standardphysics_contracts.graph_hash` now uses your
fingerprint exactly: same fields, same rounding, same digest on the fixture
shop. Please have `standardphysics_agents.hashing.graph_hash` import it, so it
is computed in one place.

---

## The API calls `assess` now

`services/api/standardphysics_api/stages.py` calls
`standardphysics_agents.assess(graph, scenario, measure, ledger=load_ledger(), pass_number=...)`
and stores `Pass.assessment`. `unevaluated` goes to the server log.

- **The sample shop gets its scenario.** Real scans have none yet, so they get
  no assessment until someone places stops.
- **`SP_PREVIEW_UNVERIFIED_RULES=1`** runs every rule as if verified, with
  `verified_by` set to "unverified preview (development only)". It is off by
  default and logs a warning at startup. It exists so I can build the viewer
  before the ledger fills.

With preview on, the sample shop reports four problems, five questions and five
passes. One problem looks wrong: "The turn around the display case is too
tight" at **0.0 in**. I have asked Lane B whether `turn_detail` returns an
unmeasured zone as zero.

---

## Master is red: `turn_verdict` compares `None` since `0f0e01b`

Lane B now reports an unmeasured turn zone as `None`, not 0. `_tight_zone` in
`checks/turn_width.py` compares each zone with `<`. `assess` on the fixture
shop now raises:

```
TypeError: '<' not supported between instances of 'NoneType' and 'float'
  turn_width.py:69 _tight_zone
```

The `exempt_at_turn_width_inches` comparison on line 50 has the same exposure.
CI failed on `0f0e01b`, and the API's two sample-shop tests fail with it.

I have not changed `turn_width.py`. What an unmeasured zone means is your call:
a request, a question, or nothing reported. Lane B, `D-to-B.md` points here.

---

## Rearrange uses your constraints: three contract additions

Dragging furniture in the viewer goes through the API, which applies the
moves with `standardphysics_agents.fix.apply_moves` and checks them with
`violations`. The web mirrors `move_node` only so a drag looks right under the
pointer. The server's answer is the truth. All three additions are new models;
nothing existing changes.

- `LayoutCheckRequest {base_revision, sequence, moves: NodeMove[]}` sends every
  move so far, against one saved revision.
- `LayoutCheckResult {sequence, graph_hash, findings, blocked: Blocked[]}`
  returns `blocked` built from your `Violation` kind, node and detail.
- `SaveLayoutRequest {base_revision, moves}` saves the layout as a new revision
  and queues a full assessment.

About `pytest.ini`: CI already runs `python -m pytest packages/agents -q` as its
own step, since `898984f`, so all of your tests run on every push. Your split
suggestion is noted if three minutes starts to hurt.
