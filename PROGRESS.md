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

`609db3d`, `9028d14`, `b90e570`, `d3f7d95` and `1a06655` change only the plan and lane documents. A-1 covers the lane document errors from `9028d14`.

## Lane B against its done criteria

| Criterion | State |
|---|---|
| Tape-measured doorway matches the SceneGraph within 3 cm | Blocked on the first real scan from Lane A |
| Fixture pinch comes back as 31 in with the right coordinate | Met |
| Lane C calls the real functions instead of stubs | Not yet; Lane C has not pushed |

Build order tasks 4 (USDZ import), 8 (Astra label), 9 (Astra clean) and 11 (finding renders) are not done. `PROGRESS_B.json` lists the `MeasurementProvider` as done, which A-9 and A-10 contradict.

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
High. `blocked` on Lane D and a person approving `Stop.anchor_node_id`; see `docs/handoffs/audit-to-D.md`.

`routes.ENDPOINT_EXEMPTION` ignores every cell within 0.75 m of each stop so a counter does not set its own route's bottleneck. The entrance stop sits 0.3 m inside the front wall, so the doorway itself is exempt, and so is anything placed just inside it. The exemption was disclosed in the first `B-to-C.md` and dropped from the rewrite in `d1cd65a`.

Reproduced: a 20 in gap 0.2 m inside the entrance reports **31.00 in**. The same gap 1.2 m inside reports 20.00 in.

### A-7 The measurement cache ignores object size
Medium. `fixed in 77dd362`.

`measure._signature` keys the cached grid on node ID, `m[3]`, `m[7]` and `m[0]`. Resizing an object reuses the old grid, and so does any rotation that leaves `m[0]` unchanged, such as the same angle in the other direction.

Reproduced: seal the aisle by widening `case_east` without moving it. The provider that already measured the shop returns **reachable=True, 0.00 in**; a fresh provider returns reachable=False.

### A-8 The counter approach ignores the counter's rotation
High. `fixed in 77dd362`.

`counter_approach` always places the 48 by 30 in clear floor space on the counter's minus-Y side, using the unrotated depth. The code calls this a forward approach, but a 48 in side running along the counter is the parallel-approach orientation.

Reproduced: rotate the counter 90 degrees. Its footprint spans x -0.35 to 0.35 and y 2.00 to 5.20, the approach centre lands at (0.00, 2.87) **inside the counter**, and the check returns **fits=True**.

### A-9 Door clear width reports the door leaf
Medium. `blocked` on Lane D and a person approving `WidthResult.needs_measurement`; see `docs/handoffs/audit-to-D.md`.

`door_clear_width` returns the larger dimension of the door node. ADA 2010 404.2.3 measures between the door face and the stop with the door open 90 degrees, which is narrower than the leaf. A door whose leaf is 32 in passes while its clear width fails.

Reproduced: the fixture's 0.900 m door reports 35.43 in with no deduction. `WidthResult` has no field for "needs a measurement", so an honest fix needs a contract change.

### A-10 The 180 degree turn width is the route width
Medium. `open`.

Build task 7 requires clear width at a 180 degree turn, which is a tier 1 check in `LANE_C.md` (ADA 2010 403.5.2). `turn_clear_width` returns `route_clear_width`. `B-to-C.md` discloses this, but `PROGRESS_B.json` marks the provider done.

### A-11 Ingest invents a confidence when the export has none
Medium. `fixed in 77dd362`.

`ingest._node` reads `element.get("confidence", "high")`, so an element with no confidence becomes `quality="measured"`. The module says the parser raises rather than inventing a value, and the plan treats unverified geometry as needing another look.

### A-12 GLB export has no automated test
Low. `open`.

`export_glb` and `glb_node_names` have no test, and CI has no Blender. Checked by hand: the committed `shop.glb` has 19 nodes, each named with its SceneGraph node ID.

### A-13 Region loci are always axis-aligned squares
Low. `fixed in 2a5f763`. Callers still have to pass the counter's rotation and `circle=True` for a turning space.

`region_locus` draws an axis-aligned rectangle with a camera fixed to look from minus Y. A turning space is a 60 in circle, and a rotated clear floor space draws in the wrong orientation once A-8 is fixed.
