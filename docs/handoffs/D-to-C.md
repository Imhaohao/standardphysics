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

---

## The report reads your ledger

`GET /api/scans/{id}/report` returns a new contract, `Report`: the scan,
scene, scenario and latest assessment, plus `rules: ReviewedRule[]` with
`{check, verified_by, verified_at, second_check_by}`. It is built from
`load_pack()` and the same ledger `assess` uses, and it lists only the rules the
ledger verifies. The printed report's "What we checked" table shows the
section, the check title, the standard (threshold and unit), and who reviewed
it and when. With `SP_PREVIEW_UNVERIFIED_RULES=1` the reviewer reads
"unverified preview (development only)", so a preview report never passes as a
reviewed one.

---

## The fixture counter is 47 in, from the lawsuit in the pitch

The demo now follows Whitaker v. T Rock Inc. (N.D. Cal. No. 5:22-cv-00283). The
complaint, paragraph 12, puts the counter at about 47 inches, and the fixture
counter now stands exactly 47 in. Lane D's person asked me to adjust what the
change broke, so this push edits two numbers in your lane:

- `evaluation/dataset.py`: `FIXTURE_COUNTER_INCHES` goes from 43.307 to 47.0
- `tests/test_checks.py`: the counter finding expects 47.0

Your copy already reads well against it: "It's 47 inches high. Ordering from a
wheelchair needs 36 inches or lower", and the fix "Add a lower section to the
ordering counter. Make it 36 inches long and 36 inches high" matches what the
deck shows. `test_the_router_picks_the_right_action_every_time` fails before
and after this change, at 31 of 32. That is audit A-41, your label for
`blocked_but_movable`.

---

## `Assessment.rules_checked`, for audit A-44

`Assessment` gains `rules_checked: int | None = None`, and the API sets it after
calling `assess`: `len(load_pack().enabled(ledger, max_tier=1))`. A shop with
zero findings then reads "Everything we checked passes" only when rules
actually ran. With none verified, it reads "Checks start once a person reviews
the rules". If you would rather set it inside `assess`, say so and I will drop
the API's copy.

---

## Answer to "who places the stops": the owner, from a suggestion

Neither real phone scan has a door or a counter. They are rooms of tables,
chairs and one storage unit. So a route cannot be read off the scan, and
checking a guessed one would report findings that are not true.

What the API does now:

- **`GET /api/scans/{id}/scenario/suggestion`** proposes Entrance, Counter,
  Pickup, Seat and Exit. It uses the largest door if there is one, and anything
  labelled "counter" and the table nearest the room's middle. Otherwise it picks
  spots along the room's edges. Each stop is snapped onto open floor with 45 cm
  of standing room, at least 1 m from the other stops, inside the walls. Anchors
  point at the door, counter and table when those exist. It is never assessed on
  its own.
- **`PUT /api/scans/{id}/scenario`** is how the owner confirms or moves the
  route in the viewer. It saves the scenario and queues `assess` again.

On `ravida`, with every rule in preview, the confirmed route reports "The path
to where you pick up drinks is too narrow", 13.8 in, plus the photo requests.
When Astra can name stops, its answer replaces
`services/api/standardphysics_api/scenario.py`, and the owner still gets to
move them.

---

## The lawsuit counter as the complaint describes it: a check to ask for

The public complaint in Whitaker v. T Rock Inc. (5:22-cv-00283, paragraph 12)
says more than the 47 inches: "While there was a lowered section, transactions
take place at the higher counter, which is located about 47 inches above the
finish floor. The point-of-sale machines were located on the higher counters."
The problem was where people pay, not a missing lowered section.

`standardphysics_fixtures.build_lawsuit_graph()` and `build_lawsuit_scenario()`
model that:

- **High counter.** It keeps the `counter` node ID and label, is 47 in high and
  is 90 in long.
- **Lowered section.** `counter_lowered`, labelled "Lowered counter section", is
  36 in long and 36 in high, at the west end. Your role table does not treat it
  as a service counter.
- **Card reader.** `card_reader`, labelled "Card reader", is movable and sits on
  the high section near its front.
- **Counter stop.** It stands in front of the high section.

`build_graph()` itself is unchanged. Splitting its counter broke 13 of your
tests: ask answers, protruding objects, evaluation cases and the router. They
belong to you to update, so I didn't.

On the variant your checks report the counter at 47 in, with the fix "Add a
lower section to the ordering counter". That fix is wrong when one exists. What
would match the case, and the pitch deck:

- **A check:** the point of sale sits on a section higher than 36 in when a
  lowered section exists (904.4 and the 904.2 advisory about the register). It
  needs a person to verify it, like every rule.
- **A fix:** "Move the card reader to the lowered counter."

When that lands, the sample shop seed switches to the lawsuit variant with a
one-line change in `services/api/standardphysics_api/seed.py`.
