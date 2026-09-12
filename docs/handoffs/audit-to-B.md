# Audit to B: fixes landed in your files

These fix findings in `PROGRESS.md`. Each has a regression test in `tests/test_audit_lane_b.py` that fails on `d1cd65a`. Pull before you edit these files again.

| Finding | File | Change |
|---|---|---|
| A-5 | `occupancy.py` | `BLOCKING_HEIGHT` is 1/4 in, from ADA 2010 303. At 0.23 m a 7.9 in planter across the aisle read as open floor. Person C should confirm the value against the source. |
| A-7 | `measure.py` | The grid cache keys on the full transform, dimensions and kind. Resizing a node used to reuse the old grid. |
| A-8 | `measure.py`, `footprints.py` | `counter_approach` places and turns the 30 by 48 in space with the counter, in front of its local minus-Y face. `footprints.rotation_about_z` is the shared helper. |
| A-11 | `ingest.py` | An element with no `confidence` gets `needs_another_look` instead of `measured`. |
| A-2 | `check_blender.py` | `blender_path` tries `$BLENDER`, then `blender` on `PATH`, then the macOS app. |
| A-12 | `tests/test_audit_lane_b.py` | Checks the committed `shop.glb` names every node by ID, and a fresh export where Blender is installed. |
| A-13 | `locus.py` | `region_locus` takes `rotation` and `circle`. Pass the counter's rotation for its clear floor space and `circle=True` for a turning space. |

## Still open in your lane

- **A-14, A-15:** fixed by the audit in `turns.py`. Each 403.5.2 width is now the exact gap from the pivot to the obstacle facing it. Grid clearance at the apex reads a 48 in turn as 41 in and a 60 in turn as 35 in, and the old approach zone could read 0. `tests/test_audit_turns.py` pins real widths.
- **A-6:** route width still ignores everything near a stop instead of only its `anchor_node_id`. The audit is fixing this in `routes.py` and `measure.py`; say so in a handoff if you would rather take it.
- **A-9:** `door_clear_width` should set `needs_measurement=True`. The audit is fixing this alongside A-6.
- **A-22:** leg 1's 29.79 in is not a pinch the route crosses. The counter and table_1 do not overlap in x, and the grid width where the route passes is 57 in. Details in `PROGRESS.md`.
