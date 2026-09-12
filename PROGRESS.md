# Audit log

Every push to `master` is audited against its lane document, the plan's invariants, `packages/contracts`, CI on the pushed commit, path ownership in `docs/AGENT_PROTOCOL.md`, and whether `PROGRESS_<LANE>.json` matches the code. A finding is recorded only after it is reproduced by running code or read directly from the diff.

Status is one of `open`, `fixing`, `fixed in <commit>`, or `blocked` with the person or lane it waits on.

## Pushes

| Push | Lane | Verdict | Findings |
|---|---|---|---|
| `21bbc65` Add shared contracts, fixture shop, and the upload contract | D | Pass with notes | A-1 |
| `a95c77e` B: Blender check and coordinate conversion | B | Pass with notes | A-2, A-3 |
| `1a6487e` B: occupancy grid, widest path, and exact clearance measurement | B | **Fail** | A-4, A-5, A-6, A-7, A-8, A-9, A-10 |
| `bb6e303` B: parse CapturedRoom exports into a SceneGraph | B | Pass with notes | A-3, A-11 |
| `d0d0ea5` B: GLB export, and reconcile the lane docs with OpenRouter | B | Pass with notes | A-3, A-12 |
| `d2a982a` Fix CI: install packages/pipeline | B | Pass | Resolves A-4 |
| `d1cd65a` B: build the locus that points a finding at the model | B | Pass with notes | A-13 |
| `28e64c1` B: implement ADA 403.5.2, and convert scanned USDZ | B | **Fail** | A-14, A-15, A-16 |
| `a4eb74a` B: render findings for the report | B | Pass with notes | A-17 |
| `9dd969d` D: announce contract fields and the assess seam | D | Pass | Reports A-20, A-21 |
| `9ced7bc` C: rule pack, tier 1 checks, finding copy | C | Pass with notes | A-23, A-24 |
| `b5306c8` D: stop anchors, needs_measurement, graph_hash, street scenario | D | Pass | Resolves A-21; unblocks A-6 and A-9 |
| `0132fb2` B: cut doorways out of walls, bound the search | B | Pass with notes | Resolves A-20; A-6 still open; handoff misreads A-22 |
| `898984f` D: rule units, contract vocabulary, Lane C in CI | D | Pass with notes | Resolves A-23 and A-24; A-18 |

`609db3d`, `9028d14`, `b90e570`, `d3f7d95` and `1a06655` change only the plan and lane documents. A-1 covers the lane document errors from `9028d14`.

## Lane B against its done criteria

| Criterion | State |
|---|---|
| Tape-measured doorway matches the SceneGraph within 3 cm | Blocked on the first real scan from Lane A |
| Fixture pinch comes back as 31 in with the right coordinate | Met |
| Lane C calls the real functions instead of stubs | Met in `9ced7bc` |

Tasks 8 (Astra label) and 9 (Astra clean) wait on an OpenRouter key. Task 4 is covered by `usdz_to_glb`, which has not met a real RoomPlan export. `PROGRESS_B.json` lists the 403.5.2 turn rule as done, which A-14 and A-15 contradicted until the audit fix.

## Findings

### A-1 Lane documents point at files that do not exist
Low. `fixed in 7fb2d22`.

`LANE_A.md` names `packages/fixtures/mock_api.py` and `python -m fixtures.mock_api`; the module is `standardphysics_fixtures.mock_api`, which the README gets right. `LANE_B.md` and `LANE_C.md` name `packages/fixtures/shop.room.json`; no room.json fixture exists, only `data/shop.scene_graph.json`. `LANE_C.md` names `packages/fixtures/stub_measurements.py`; it lives at `packages/fixtures/standardphysics_fixtures/stub_measurements.py`.

### A-2 The Blender self-test only works on a Mac with Blender in /Applications
Low. `fixed in 2a5f763`.

`check_blender.BLENDER` is hard-coded to `/Applications/Blender.app/Contents/MacOS/Blender`, with no fallback to `blender` on `PATH`. The lane document asks for a check every machine can run.

### A-3 Lane B pushes edit files outside Lane B's paths
Low. `blocked` on Boris agreeing who owns root files and `tests/`.

Lane B owns `packages/pipeline/**`, `PROGRESS_B.json` and `docs/handoffs/B-to-*.md`. Its pushes also changed `pytest.ini` (`a95c77e`), `.gitignore` and `.env.example` (`bb6e303`), `docs/lanes/LANE_C.md`, `docs/lanes/LANE_D.md` and Lane D's `packages/fixtures/standardphysics_fixtures/data/shop.glb` (`d0d0ea5`), and `.github/workflows/ci.yml` and `pyproject.toml` (`d2a982a`). No damage found, but the protocol says to write a handoff instead.

### A-4 CI was red from `1a6487e` through `1a06655`
High. `fixed in d2a982a`.

CI never installed `packages/pipeline`, so `numpy` was missing and `test_coords.py`, `test_ingest.py` and `test_measure.py` failed to import. Five pushes landed on a red `master`. `d2a982a` adds the package; CI is green on `d2a982a` and `d1cd65a`, and 54 tests pass in a clean environment.

### A-5 Solid obstructions under 9 inches are treated as open floor
High. `fixed in 77dd362`. Person C still needs to verify the 1/4 in value against the source.

`occupancy.BLOCKING_HEIGHT = 0.23` lets anything lower than 9 in be rolled over, citing toe clearance. Toe clearance is space beneath an element; it does not make a solid object passable. ADA 2010 303 allows at most 1/4 in of vertical change untreated and requires a ramp above 1/2 in. This breaks the lane rule that no allowance may shrink an obstacle.

Reproduced: a solid 7.9 in tall barrier across leg 0, 1.2 m from the entrance, reports **31.00 in, reachable**.

### A-6 The endpoint exemption hides obstructions at the entrance
High. `open`. `Stop.anchor_node_id` landed in `b5306c8`. `0132fb2` made the exemption shrink on short legs but still ignores the anchor.

`routes.ENDPOINT_EXEMPTION` ignores every cell within 0.75 m of each stop so a counter does not set its own route's bottleneck. The entrance stop sits 0.3 m inside the front wall, so the doorway itself is exempt, and so is anything placed just inside it. The exemption was disclosed in the first `B-to-C.md` and dropped from the rewrite in `d1cd65a`.

Reproduced: a 20 in gap 0.2 m inside the entrance reports **31.00 in**. The same gap 1.2 m inside reports 20.00 in. Reproduced again at `0132fb2`.

### A-7 The measurement cache ignores object size
Medium. `fixed in 77dd362`.

`measure._signature` keys the cached grid on node ID, `m[3]`, `m[7]` and `m[0]`. Resizing an object reuses the old grid, and so does any rotation that leaves `m[0]` unchanged, such as the same angle in the other direction.

Reproduced: seal the aisle by widening `case_east` without moving it. The provider that already measured the shop returns **reachable=True, 0.00 in**; a fresh provider returns reachable=False.

### A-8 The counter approach ignores the counter's rotation
High. `fixed in 77dd362`.

`counter_approach` always places the 48 by 30 in clear floor space on the counter's minus-Y side, using the unrotated depth. The code calls this a forward approach, but a 48 in side running along the counter is the parallel-approach orientation.

Reproduced: rotate the counter 90 degrees. Its footprint spans x -0.35 to 0.35 and y 2.00 to 5.20, the approach centre lands at (0.00, 2.87) **inside the counter**, and the check returns **fits=True**.

### A-9 Door clear width reports the door leaf
Medium. `open`. `WidthResult.needs_measurement` landed in `b5306c8`; at `0132fb2` `door_clear_width` still returns it as false.

`door_clear_width` returns the larger dimension of the door node. ADA 2010 404.2.3 measures between the door face and the stop with the door open 90 degrees, which is narrower than the leaf. A door whose leaf is 32 in passes while its clear width fails.

Reproduced: the fixture's 0.900 m door reports 35.43 in with no deduction. `WidthResult` has no field for "needs a measurement", so an honest fix needs a contract change.

### A-10 The 180 degree turn width is the route width
Medium. Superseded by `28e64c1`, which measures the turn; see A-14 and A-15.

Build task 7 requires clear width at a 180 degree turn, which is a tier 1 check in `LANE_C.md` (ADA 2010 403.5.2). `turn_clear_width` returns `route_clear_width`. `B-to-C.md` discloses this, but `PROGRESS_B.json` marks the provider done.

### A-11 Ingest invents a confidence when the export has none
Medium. `fixed in 77dd362`.

`ingest._node` reads `element.get("confidence", "high")`, so an element with no confidence becomes `quality="measured"`. The module says the parser raises rather than inventing a value, and the plan treats unverified geometry as needing another look.

### A-12 GLB export has no automated test
Low. `fixed in 750045b`. CI has no Blender, so only the committed file is checked there.

`export_glb` and `glb_node_names` have no test, and CI has no Blender. Checked by hand: the committed `shop.glb` has 19 nodes, each named with its SceneGraph node ID.

### A-13 Region loci are always axis-aligned squares
Low. `fixed in 2a5f763`. Callers still have to pass the counter's rotation and `circle=True` for a turning space.

`region_locus` draws an axis-aligned rectangle with a camera fixed to look from minus Y. A turning space is a 60 in circle, and a rotated clear floor space draws in the wrong orientation once A-8 is fixed.

### A-14 Turn widths measure the pivot's corner, not the gap
High. `fixed` by the audit commit *measure 180 degree turn widths as exact gaps from the pivot*.

`28e64c1` measured each 403.5.2 width as grid clearance times two at points on the route. At a turn that is the distance to the pivot's corner rather than to the wall across from it, and the approach zone can start inside an occupied cell.

Reproduced on a room with 42 in lanes and a 48 in turn, which meets the rule: approaching **0.00**, at the turn **41.34**, leaving **41.34**, and `turn_clear_width` returns **0 in**. In `tests/test_turns.py`'s own U-shaped shop the leaving width reads 37.40 in against a real 149.61 in. The fix measures each width as the exact footprint gap from the pivot to the obstacle facing it; detection and the pivot are unchanged.

### A-15 The 60 inch exemption never applies
High. `fixed` by the audit commit *measure 180 degree turn widths as exact gaps from the pivot*.

The same undermeasurement reads a 60 in turn as 35.43 in, so 403.5.2's exception cannot trigger. Reproduced on a room with 36 in lanes and a 60 in turn: `in_scope=True`, `passes=False`.

### A-16 The turn tests check no measured width
Medium. `fixed` by `tests/test_audit_turns.py`.

`tests/test_turns.py` asserts only that each width is above zero and that a pivot exists, so A-14 and A-15 shipped with CI green, and `B-to-audit.md` reported A-10 fixed on that basis. Lane C's 105 tests also pass with and without the fix, so nothing downstream caught it either.

### A-17 A report camera can sit outside the room
Low. `open`.

`a4eb74a` sizes the framing from the blocking objects. For a pinch between the south wall and a table 30 in from it, the camera lands at (-3.19, -3.57, 7.04), past the wall at x = -3. It is 7 m up, so the wall may not block the view. `tests/test_render.py` checks only the y coordinate.

### A-18 Lane D's push edits Lane C's files
Low. Noted.

`898984f` changes `packages/agents/standardphysics_agents/rules/pack.py` and `packages/agents/tests/test_rulepack.py`. The commit says Lane D's person approved it and asked for the one caller to be fixed in the same push; the protocol asks for a handoff instead.

### A-20 Walls seal their doorways
High. `fixed in 0132fb2`. Reported by Lane D in `9dd969d`.

Reproduced at `28e64c1`: 19 of 19 samples across the front door belong to the south wall, and a stop 1 m outside the door cannot reach the counter. At `0132fb2` that route reaches the counter at 31 in.

### A-21 The Seat stop stood inside a table
Medium. `fixed in b5306c8`. Reported by Lane D in `9dd969d`.

Reproduced: Seat sat at (-2.0, -2.4), the centre of table_3, and leg 3 measured 6.89 in from inside the table. It now measures 79.23 in.

### A-22 A route width is taken from two obstacles the route never passes between
High. `open`; the audit fix is in progress.

`measure._exact_width` reports the footprint gap between the two obstacles nearest the pinch whether or not the route passes between them. Leg 1, Counter to Pickup, reports **29.79 in** between the counter's corner and table_1. The counter spans x -1.6 to 1.6 and table_1 spans x -2.3 to -1.7, so the walk from x -0.8 to x 0.8 never goes between them, and the grid width at the pinch is **57.09 in** at `0132fb2`. `B-to-D.md` in `0132fb2` calls this a real pinch, and `C-to-B.md` treats it as a second route finding.

### A-23 Two graph hashes disagreed
High. `fixed in 898984f`.

At `b5306c8`, `contracts.graph_hash` and Lane C's `hashing.graph_hash` returned different hashes for the same fixture, so an assessment and a proposal could not agree on whether a layout was stale. At `898984f` they match, including after a change of quality.

### A-24 Lane C's tests did not run in CI
Medium. `fixed in 898984f`.

`pytest.ini` collects only `tests/`, and CI did not install `packages/agents`, so `9ced7bc`'s 105 tests never gated `master`. `898984f` installs the package and runs them.
