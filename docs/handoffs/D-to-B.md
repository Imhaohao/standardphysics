# D to B: walls seal their doorways

## A route cannot pass through a door

`build_grid` leaves doors out of the grid, which is right. Nothing removes the
door from the wall it sits in, though, so the wall stays solid across the
opening. RoomPlan reports a wall at its full length and puts each door inside
it as a separate surface.

Reproduced at `28e64c1` on the fixture shop:

- The front door is 0.90 m wide at (0.00, -4.00), and the south wall runs 6 m
  along the same line.
- 17 of 17 samples taken 5 cm apart across the door opening are occupied, and
  the wall owns every one.
- A stop 1 m outside the door has no route to the counter.
  `route_clear_width` returns `reachable=False` with no blockers.

The tests pass only because the fixture's Entrance stop sits 0.3 m inside the
room, so no leg ever crosses the door. On a real scan, any route that starts
outside or leads into a back room fails. It either comes back unreachable, or
`_nearest_free` snaps the stop to the other side of the wall.

**Suggested fix:** mark the walls, then clear every cell that a `door` or
`opening` footprint covers. `door_clear_width` and the 404.2.4 maneuvering
check will need the opening as open floor anyway.

`build_street_scenario()` in `standardphysics_fixtures` is coming in my next
push. Its entrance stop sits 1 m outside the front door, so a regression test
can cross the doorway.

## Fixture scenario: legs 2 and 3 change, leg 0 does not

- **Seat moves.** It sits at (-2.0, -2.4), which is the centre of table_3. On
  the current code, leg 3 measures 6.89 in because the route starts inside a
  table. Seat moves to open floor beside that table. Every test in `tests/`
  uses leg 0 only.
- **Stops get anchors.** Each stop gains the `anchor_node_id` the audit asked
  for in A-6. Entrance and Exit anchor to the front wall, Counter and Pickup to
  the counter, and Seat to table_3. Nothing in your code changes until you read
  the field.

Leg 1, from Counter to Pickup, measures 29.79 in between two stops that stand
0.15 m from the counter face. Please check whether that number is the endpoint
exemption or a real pinch.

## Contract fields landing next

Both are optional, and their defaults keep today's behaviour:

- `Stop.anchor_node_id: UUID | None = None` (audit A-6)
- `WidthResult.needs_measurement: bool = False` (audit A-9)

`standardphysics_contracts.graph_hash(graph)` is coming too. Use it wherever a
graph hash is needed, so a hash computed in one lane matches another lane's.

## One ask: clearance along a route

The viewer should colour a `path` annotation by the clearance at each point.
`Annotation.points` has no values for that. If `widest_path` can return the
clearance in inches at each point, I will add an optional per-point field to
`Annotation`. Tell me whether that is cheap on your side.

---

## Update: shorter display cases, a rebuilt GLB, and `point_inches`

- **Display cases.** Each case now stops 6 inches short of its side wall
  (`CASE_WALL_GAP_INCHES`), so Lane C's documented 5 inch fix is a legal move.
  The aisle is still exactly 31 in, and the fix still reaches 36.
- **Two of your tests.** Both sealed the aisle by widening `case_east` until it
  met `case_west`, which now leaves a 6 in route past the wall. Each test now
  stretches `case_east` wall to wall instead, and checks the same thing:
  - `tests/test_measure.py::test_a_blocked_route_reports_unreachable`
  - `tests/test_audit_lane_b.py::test_a7_resizing_an_object_rebuilds_the_cached_grid`
- **Rebuilt files.** `shop.glb` and `shop.usdz` are rebuilt from the new graph
  with Blender 5.2.1.
- **`point_inches`.** `Annotation.point_inches: list[float | None] | None` is
  in. Please return `None` for points inside the exemption, as you offered. The
  viewer will then colour only the values that mean something.

---

## Urgent: on a real scan the floor is not at z = 0

`packages/fixtures/standardphysics_fixtures/data/real/` now holds two real
RoomPlan exports from Apple's WWDC23 sample (MIT-style licence, notice
included). Each has `room.json`, the mapping file and the USDZ. `parse_room_json`
reads all 11 rooms in that sample without an error.

RoomPlan puts the origin wherever the phone started, so the floor of a real
scan sits about 1.4 m below z = 0. `blocks_floor` compares an object's top
against `BLOCKING_HEIGHT` in absolute z, which gets both directions wrong. In
`apple_livingroom.room.json` the floor is at z = -1.436:

| Object | Bottom | Top | `blocks_floor` |
|---|---|---|---|
| Sofa (3 of them) | -1.436 | -0.558 | **False** |
| Table (2) | -1.436 | -0.974 / -0.927 | **False** |
| Oven | -1.436 | -0.546 | **False** |
| Television, wall-mounted | -0.224 | +0.620 | **True** |
| Storage, wall-mounted | -0.463 | +0.979 | **True** |

So every sofa and table reads as open floor, and a wall-mounted cabinet whose
underside is 0.97 m up reads as a floor obstruction. Counter height, camera
eye height and render framing all assume the same floor.

**Suggested fix:** in ingest, shift every node so the floor's z is 0, then let
nothing else change. Measure a blocker by its bottom as well as its top, so an
object whose underside clears 27 in stays out of the floor grid and belongs to
the protruding-objects check instead.

Two other things the real files settle for you:

- **`parentIdentifier`.** Every door, window and opening carries its parent
  wall's identifier. Reading it into `SceneNode.parent_id` tells the doorway
  carve-out exactly which wall to cut.
- **The mapping file is a binary plist** (`bplist00`), not JSON, even though
  Lane A names it `room.metadata.json`. Read it with `plistlib.loads`.
  `usdz_to_glb` should accept both.
- **Unknown top-level keys.** Real exports carry `coreModel` (a base64 blob,
  60-90% of the file), `sections`, `story` and `version`. Newer ones also carry
  `referenceOriginTransform`. None has a top-level `identifier`.

`tests/test_real_exports.py` pins what already works.

---

## `usdz_to_glb` on a real export: the mapping is a plist

The API now runs your stages on uploads. I replayed Apple's real living room
(`data/real/apple_livingroom.*`) through upload, finalize and the job queue with
Blender 5.2.1:

- `parse_room_json` produced the graph, and the scan was ready in about 2
  seconds.
- `usdz_to_glb` opened the USDZ, taking 35 ms, but printed no `USDZ_CONVERTED`.
  `load_map` calls `json.loads` on the mapping file, and a real mapping is a
  binary plist. Try `plistlib.loads` first and fall back to JSON. The API names
  the file `room.metadata.plist` when its bytes start with `bplist`, and
  `room.metadata.json` otherwise.
- The API fell back to `export_glb`, which named all 22 GLB nodes by SceneGraph
  ID.

## A finding at 0.0 inches on the sample shop

With every rule verified for preview, the fixture reports "The turn around the
display case is too tight" measured at **0.0 in**. The aisle and counter
findings read 31.0, 29.79 and 43.3 as expected. A 0.0 in turn looks like
`turn_detail` returning an unmeasured zone as zero. Lane C sees it too.

---

## `0f0e01b` broke Lane C's turn check

Returning `None` for an unmeasured turn zone is right. Lane C's
`turn_verdict` still compares each zone with `<`, so `assess` now raises on
the fixture shop, and CI on `0f0e01b` is red. Details are in `D-to-C.md`.
Please agree the fix with Lane C before either of you pushes it.
