# B to D: the floor bug is fixed, and the real exports settled four guesses

That report was exact enough to fix in one pass. Thank you for finding it —
every measurement this lane produces would have been wrong on real data, and
nothing in the fixture could have caught it because our floor was already at
zero.

## Fixed

**The room now stands on its floor.** `parse_room_json` shifts every node so
the floor sits at z = 0, once, on ingest. Nothing downstream needs to know where
the phone was standing, and heights are heights above the floor everywhere after
that. `apple_livingroom` comes in at -1.436 and lands at 0.000.

**`blocks_floor` reads both ends of an object.** A node takes up floor space
only when its top clears 1/4 in *and* its underside is below 27 in. Above that,
ADA 2010 307 handles it as a protruding object. On the living room: three sofas,
two tables and the oven now block; the wall-mounted television at 1.212 m and
both wall cabinets at 0.97 m do not. Person C has the 27 in for verification
with the rest of the thresholds.

**`parent_id`.** Every door, window and opening now carries its parent wall.
22 of 22 across both rooms.

**The mapping file reads either way.** `usdz_to_glb` sniffs for `bplist00` and
falls back to JSON, so it takes Lane A's `.json` and a real `.plist` without
being told which it has.

## One correction to your numbers

A real USDZ imports more objects than it has meshes. Apple's living room is 37
objects, of which 19 are geometry and 18 are USD grouping nodes — `Object_grp`,
`Section_grp`, `new_floorplan`, the room itself. They hold nothing a check could
reason about and the mapping file rightly ignores them.

`ConversionResult` now counts identity over meshes, and gains a `meshes` field:

| Room | Imported | Meshes | Renamed | Identified |
|---|---|---|---|---|
| `apple_livingroom` | 37 | 19 | 19 | yes |
| `apple_bedroom3` | 26 | 11 | 11 | yes |

Before this, both read as `fully_identified=False` and looked broken when they
were not.

## Still open, and it is still yours

The leg 1 scenario question from the last handoff stands: Counter to Pickup is
not a journey, and no exemption geometry fixes that. Drop the leg or move
Pickup.

`tests/test_real_ingest.py` has 16 tests against both rooms. 136 pass.
