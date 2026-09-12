# Audit to B: fixes landed in your files

These fix findings in `PROGRESS.md`. Each has a regression test in `tests/test_audit_lane_b.py` that fails on `d1cd65a`. Pull before you edit these files again.

| Finding | File | Change |
|---|---|---|
| A-5 | `occupancy.py` | `BLOCKING_HEIGHT` is 1/4 in, from ADA 2010 303. At 0.23 m a 7.9 in planter across the aisle read as open floor. Person C should confirm the value against the source. |
| A-7 | `measure.py` | The grid cache keys on the full transform, dimensions and kind. Resizing a node used to reuse the old grid. |
| A-8 | `measure.py`, `footprints.py` | `counter_approach` places and turns the 30 by 48 in space with the counter, in front of its local minus-Y face. `footprints.rotation_about_z` is the shared helper. |
| A-11 | `ingest.py` | An element with no `confidence` gets `needs_another_look` instead of `measured`. |
| A-2 | `check_blender.py` | `blender_path` tries `$BLENDER`, then `blender` on `PATH`, then the macOS app. |
| A-13 | `locus.py` | `region_locus` takes `rotation` and `circle`. Pass the counter's rotation for its clear floor space and `circle=True` for a turning space. |

## Still open in your lane

- **A-10:** `turn_clear_width` still returns the route width. Tier 1 needs ADA 2010 403.5.2.
- **A-12:** GLB export needs a test.

A-6 and A-9 wait on the contract changes in `audit-to-D.md`.
