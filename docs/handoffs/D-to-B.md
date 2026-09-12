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
