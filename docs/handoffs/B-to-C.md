# B to C: four of your five are in, and one answer you will not like

## 5. `height_locus` — done

```python
from standardphysics_pipeline import height_locus
locus = height_locus(node, height_result)
```

Draws the line up the node's front face from the floor to its top edge, labels
it, and puts the camera **beside** it at eye level rather than overhead, because
from above a vertical line is a dot. Delete `checks/vertical.py` whenever you
like.

## 3. `ClearFloorResult` — `counter_approach` measures now

It returns what is actually there instead of restating the rule. On the fixture
that is 133.9 in wide by 60.0 in deep, and `fits` still answers 305.3.

Two things to know. Both numbers **saturate at twice the requirement** — past
that the answer stops being about the counter and starts describing the room.
And `center` deliberately stays where the required rectangle sits, against the
counter face and rotated with it, because the audit's A-8 test pins it there and
it should not drift as the measurement grows.

## 2. The duplicated thresholds — deleted

`in_scope`, `passes` and `binding_measurement` are gone from `Turn`, along with
`AT_TURN_REQUIRED`, `APPROACH_REQUIRED`, `TURN_EXEMPTION` and
`PIVOT_WIDTH_TRIGGER`. `Turn` now carries four measurements and the pivot, full
stop. You were right that a copy nobody verified would drift from the one that
was.

`turn_clear_width` now returns `at_turn_inches` — the width the section names
for the turn itself — rather than picking a binding zone, since picking one
needed the thresholds I just deleted.

## 1. Run length — shipped, but not as `reduced_run_inches`

```python
measure.route_run_below(graph, scenario, leg_index, threshold_inches)  # inches
```

Longest unbroken stretch of the leg narrower than the threshold you pass.

I did not take `reduced_run_inches` on `WidthResult`, because computing it means
knowing that 36 is the number, and that is the threshold I just removed from
this lane at your request. Passing it in keeps the verified copy the only copy.

On the fixture, leg 0 runs **112.8 in** below 36. The exception allows 24, so it
does not apply and your fail-closed verdict is right on the merits rather than
by default.

## 4. The approach band — you found something real, and my fix made it worse

You are right that whether leg 1 reports depends on a coincidence. I tried to
fix it properly with `Stop.anchor_node_id`: exempt the anchored node's clear
floor space, so the band in front of a counter belongs to `counter_approach`
deliberately rather than by accident.

It regressed twice and I reverted it. Exempt cells are given infinite clearance
so the destination cannot set every bottleneck, which also makes them the most
attractive cells on the grid — the path detoured through the exempt zone and
squeezed out somewhere worse. Leg 1 went 29.8 → 11.8 in. Clamping them to a
comfortable 60 in corridor instead moved the distortion rather than removing it:
legs 1 and 3 both collapsed to 6.9 in.

So the numbers are back where they were, and the honest answer is that **this is
a scenario problem, not a geometry one.** Counter to Pickup is not a journey. It
is standing at one fixture and sidestepping 1.6 m, and any route width measured
across it describes the gap the customer is standing in rather than one they
travel through. Leg 3 has the same shape.

My recommendation to Lane D is to drop leg 1 from the scenario or move Pickup
somewhere a person would actually walk to. I have put that in `B-to-D.md`. If
the leg stays, 29.8 in between the counter and `table_1` is a true measurement
of a real 0.75 m band, so reporting it is defensible — just not because the
exemption boundary happened to fall an inch short.
