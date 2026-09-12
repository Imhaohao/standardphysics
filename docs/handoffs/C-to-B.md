# C to B: five things from wiring the checks to your provider

Tier 1 runs against `PipelineMeasurements` now. The 31 inch aisle comes back as
exactly one route width finding citing 403.5.1, with both display cases named
and `width_locus` drawing `31 in` across the gap. The counter height comes back
as a second finding. Thank you for both, and for `turn_detail`.

## 1. 403.5.1's exception needs a run length

The section is 36 inches, and its exception permits 32 for a run of 24 inches
maximum between segments at least 48 long and 36 wide. A bottleneck measurement
cannot settle the length condition, so anything between 32 and 36 inches fails
closed here rather than passing on a condition nobody evaluated.

**Ask:** `WidthResult.reduced_run_inches: float | None = None` — how far the
sub-36 stretch runs along the direction of travel. `route_width_verdict` already
reads it off the result with `getattr`, so the exception starts being evaluated
the moment you set it and nothing in Lane C changes.

## 2. 48 inches lives in two places

`turns.py` holds `AT_TURN_REQUIRED = 48.0`, `APPROACH_REQUIRED = 42.0` and
`TURN_EXEMPTION = 60.0`. The rule pack holds the same four numbers with the
quoted sentence from 403.5.2 and a person's name against them.

I use `turn_detail`'s four measurements and ignore `in_scope`, `passes` and
`binding_measurement`, so the verdict comes from the pack. That keeps the demo
honest, but it leaves your copies live: a person verifying the pack has not
verified `turns.py`, and the two can drift apart silently.

**Ask:** treat `approach_inches`, `at_turn_inches`, `leaving_inches` and
`pivot_width_inches` as the contract and the verdict properties as a
convenience nobody depends on. If you would rather delete them, nothing here
breaks.

Your two disclosed approximations are noted and go to the human in this lane
with the rest of the threshold review: the pivot's smaller horizontal extent as
the "width" in 403.5.2, and geometric turn detection at about 122 degrees.

## 3. `ClearFloorResult` means two different things

`turning_space` returns the space it measured. `counter_approach` returns the
space the rule requires — `to_inches(COUNTER_CLEAR_WIDTH)` by
`to_inches(COUNTER_CLEAR_DEPTH)`, always 48 by 30 — and puts the answer in
`fits`.

A check reading `inches_wide` gets a measurement from one and a requirement from
the other. Lane C handles both by requiring `fits` **and** the named size to
meet the rule's minimum, which is correct under either reading, but the type
should mean one thing.

**Ask:** either report the measured space from `counter_approach`, or say in the
docstring that `inches_wide` and `inches_deep` name the space tested. The type
itself is Lane D's, so the same note is in `C-to-D.md`.

## 4. Leg 1 measures the counter approach

`route_clear_width(graph, scenario, 1)` — Counter to Pickup — returns 29.8 in
between the ordering counter and `table_1`, with the pinch at
`(-0.787, 2.338)`. The Counter stop is at `(-0.8, 3.1)`, so that pinch is 0.76 m
away, just outside `ENDPOINT_EXEMPTION` of 0.75 m.

It produces a real finding, and it may well be a real problem: the band between
the counter face and the tables is 29.5 in. But it lands within an inch of the
exemption boundary, so whether it is reported depends on a coincidence rather
than on geometry.

**Ask:** confirm whether the approach band belongs to `counter_approach` rather
than to the route. If it does, the exemption wants to cover it deliberately.

## 5. A height locus belongs next to the other two

The counter height finding needs a vertical dimension line, and `width_locus`
and `region_locus` do not draw one. `packages/agents/standardphysics_agents/
checks/vertical.py` builds it from your `camera_for`, which is 30 lines sitting
in the wrong lane.

**Ask:** `height_locus(node, height_result)` in `locus.py`. I will delete mine
the day it lands.
