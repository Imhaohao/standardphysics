# B to D: doorways fixed, leg 1 answered, per-point clearance shipped

Thank you for the doorway report. It was exact enough to reproduce in one go,
and it was a genuine blocker for every real scan.

## Doorways are open now

You were right about the cause: leaving doors out of the grid is not the same as
taking them out of the wall. `build_grid` now punches every `door` and `opening`
footprint back out of the occupancy after the walls are marked, with a 12 cm
bite along the door's thin axis so a panel slightly thinner than its wall cannot
leave a one cell sliver sealing the gap.

All 17 of your samples across the front door read as open floor. A stop 1 m
outside the building now routes to the counter and reports the 31 in display
case pinch rather than `reachable=False`.

**It came with a second bug attached.** Once the door opened, the search left
the building and explored the empty padding beyond the walls, where clearance is
excellent and nothing stops it. The suite went from 12 s to 91 s. The grid now
closes off everything more than 1.5 m past the floor's edge, which keeps the
pavement outside the front door walkable and the field beyond it not. All four
legs measure in 0.72 s, a street route in 0.47 s.

Those boundary cells are occupied but belong to no node, so `blockers_at` skips
them and a finding can never blame the edge of the world for a pinch.

## Leg 1 is a real pinch, not the exemption

I checked it two ways. First I made the endpoint exemption adaptive, capped at
35% of leg length, so a short leg always keeps something measurable. Leg 1 did
not move: still 29.79 in.

It is a genuine gap between the **ordering counter** and **table_1**. The
counter's front face is at y = 3.25 and the table's north face at y = 2.50,
which is 0.75 m, and the exact footprint distance is 29.79 in. Against 36 in
that is a second real route finding sitting in the fixture, so Lane C now has
two route findings and a counter height to build against.

Worth keeping the adaptive exemption regardless: a fixed 0.75 m swallowed a
1.6 m leg almost whole, and the sliver that survived sat against the counter.

## Per-point clearance: cheap, and already in

```python
measure.route_path_clearances(graph, scenario, leg_index)  # list[float], inches
```

Runs parallel to `route_clear_width(...).path`, point for point. Both come from
one sampling function, so they cannot drift out of step. Go ahead and add the
optional per-point field to `Annotation`.

One caveat for colouring. Inside the endpoint exemption the search has no
preference between cells, so the path wanders there and its clearance values are
arbitrary — leg 0 dips to 2 in a few points from the start. Those are not
findings. Either drop the first and last few points when colouring, or I can
return `None` for exempt points if you would rather handle it explicitly.

## On your contract additions

`Stop.anchor_node_id` and `WidthResult.needs_measurement` are both optional with
defaults that keep today's behaviour, so nothing in Lane B breaks. I will read
`needs_measurement` once `graph_hash` lands and wire it to nodes whose quality is
`needs_another_look`.

Send `build_street_scenario()` whenever it is ready. I have an equivalent inline
in `tests/test_measure.py::test_a_route_can_come_in_from_the_street` and will
switch to yours so there is one definition.
