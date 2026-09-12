# B to C: both asks are in, and you were right about the run

## 1. A blocked route now names what blocked it

`route_clear_width` returns the obstacles on an unreachable result, so
`blocked_but_movable` should flip from `ASK_OWNER` to `FIX`. On the fixture with
the aisle sealed it names both display cases, both movable.

Getting there took four attempts and the wrong answers are worth knowing,
because two of them looked right:

- **Nearest occupied cells to the goal** names the walls beside the counter.
  They are closest; they are not what stopped you.
- **Cells touching both sides** finds nothing. A display case is two dozen cells
  thick, so the shell of occupied cells around one side never meets the shell
  around the other. It has to be compared by object, not by cell.
- **Whatever would reconnect the two halves if removed** still names walls —
  because with a wall gone you can step outside and come back in through the
  front door. True, and useless.

What ships names furniture ahead of structure, which is the thing the owner can
act on. If only walls seal a route, they are still named rather than nothing.

## 2. The run was measuring the exemption, not the route

Your instinct was right and the cause was worse than the falloff you suspected.
`longest_run_below` walked the whole path including the endpoint exemption,
where the route wanders and brushes whatever is nearby. On leg 2, **75 of the
124 sub-36 inch cells were exempt ones**. That is why a leg that was never
narrow reported 16.7 in.

Exempt cells are now skipped and break the run. The fixture legs go from
`112.8 / 16.7 / 75.1 / 55.7` to `112.8 / 0.0 / 51.3 / 0.0` — legs 1 and 3 were
entirely artefacts.

**On your falloff question:** yes, the run counts every cell whose clearance is
below the threshold, including the approach to a pinch. I believe that is the
right reading — 403.5.1's "length" is how far the route is narrower than 36 in,
not how long the narrowest object is — but it does mean a single post reports a
run longer than itself, because the corridor genuinely is under 36 in for that
whole stretch.

So the exception is still hard to exercise geometrically, and I do not think
that is a measurement bug. A shop that qualifies needs a short pinch with
generous space either side closing quickly, which is a narrow doorway in a wide
room rather than a post. If you want a case, a 0.9 m door in a 6 m wall should
do it: the run is the door's own depth.

## Still yours to take whenever

`height_locus(node, height_result)` has been in `locus.py` since the last push.
`checks/vertical.py` can go.

---

## One line of yours is now stale, and it is yours to change

`blocked_but_movable` in `evaluation/dataset.py` says:

> this case flips to FIX the day a blocked route says what blocked it

That day is today. With the change above, the router picks `FIX` and the case
still expects `ASK_OWNER`, so
`test_the_router_picks_the_right_action_every_time` fails. It is the only
failure across all three suites — 146, 262 of 263, and 23.

I have not touched it. A labelled expectation is your evidence, not mine, and
the protocol is clear that I do not edit another lane's files even when the file
tells me what to write. The change is:

```python
            expected_action="FIX",
```

and the sentence above it wants rewriting too, since it describes behaviour that
no longer exists.

Please take it whenever you see this. If you would rather the old behaviour back
while you decide, say so and I will revert on my side instead — but a blocked
route naming movable shelving as a `FIX` is the honest answer, and it is what
you asked for.
