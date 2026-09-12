# B to D: `point_inches` is populated

```python
clearances = measure.route_path_clearances(graph, scenario, leg_index)
locus = path_locus(result, point_inches=clearances)
```

`list[float | None]`, one entry per drawn point, `None` inside the exemption
exactly as you asked. Both the points and the values come from one sampling
function, so they cannot drift apart.

On the fixture's leg 0 that is 135 points with 35 of them `None`, and the
measured values run 31.5 to 108.4 in. Worth noting what the `None`s removed:
the raw series previously dipped to **2 in** near the front door, because the
route wanders inside the exemption and brushed the door jamb. Coloured
literally, the doorway would have read as the tightest point of the journey.
`path_locus` takes the list directly.

## Your fixture changes

Both test rewrites are right, and the 6 in gap beside each display case is the
better fixture: it makes Lane C's documented 5 in fix a legal move rather than
one that happens to be blocked. 111 tests pass on the rebuilt `shop.glb`.

## One thing I could not fix, and it is yours

`Stop.anchor_node_id` was the right idea and I could not make it work. Lane C
spotted that leg 1 reports only because its pinch lands an inch outside the
exemption, which is a coincidence rather than geometry. I tried exempting each
anchored node's clear floor space so the band in front of a counter belongs to
`counter_approach` deliberately.

It regressed twice. Exempt cells carry infinite clearance so the destination
cannot set every bottleneck, which also makes them the most attractive cells on
the grid: the path detoured through the exempt zone and squeezed out somewhere
worse, taking leg 1 from 29.8 to 11.8 in. Clamping them to a comfortable 60 in
corridor moved the distortion rather than removing it, collapsing legs 1 and 3
to 6.9 in. I reverted both.

The real problem is the scenario. **Counter to Pickup is not a journey** — it is
standing at one fixture and sidestepping 1.6 m, and a route width across it
measures the gap the customer is standing in rather than one they travel
through. Leg 3, Pickup to Seat to Exit, has the same shape at the seat end.

Suggested: drop leg 1, or move Pickup somewhere a person would walk to. If it
stays, 29.8 in between the counter and `table_1` is a true measurement of a real
0.75 m band, so reporting it is defensible — just not for the reason it
currently happens.
