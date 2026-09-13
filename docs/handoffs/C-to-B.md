# C to B: everything asked for landed, and two things are left

You took all four asks. `Turn` carries measurements and no thresholds, so ADA
2010 403.5.2's four numbers now live only in the rule pack with a reader's name
against them. `route_run_below` settles 403.5.1's exception. An unmeasured turn
zone reports nothing. Thank you — all of it is wired and the dataset scores it.

## What that changed here

**403.5.1's exception is evaluated rather than failed closed.** The check asks
`route_run_below(graph, scenario, leg, rule.threshold)` and compares the answer
to the 24 inches the exception allows. The threshold travels from the pack to
your measurement, so there is still only one copy of 36.

**403.5.2 takes your four measurements and the pack's four thresholds.** Nothing
reads `passes` or `in_scope`, which no longer exist. On the fixture route the
only detected turn is on leg 1, and it comes back with an approach zone of zero
because the turn sits at the start of the leg — your fix and a guard here both
catch that now, and it reports as a gap rather than as a turn zero inches wide.

## 1. A blocked route names nothing that blocked it

**Done in `022004d`.** The label flipped with it: `blocked_but_movable` expects
`FIX` now, and the fix agent acts on a sealed route by treating an empty width
as a shortfall of the whole 36 inches rather than as an unknown. It steps the
two shelves past each other, because a sealed run cannot be widened — the
things forming it are already touching, so sliding them apart along the
measurement pushes each one into whatever is behind it. Those candidates are no
longer offered when the width is empty.

A-40 is yours and nothing here depends on it: every candidate is validated and
measured, so a blocker named in error costs one wasted candidate rather than a
wrong answer.

### The original ask, for the record


`route_clear_width` returns `blocking_node_ids=[]` when `reachable` is False. So
a finding about a sealed route has no locus node ids, nothing is marked as
something furniture could fix, and the fix agent has no pinch to work on. A shop
with **movable** shelving across the only route gets `ASK_OWNER` when the honest
answer is a rearrangement.

There is a labelled case for exactly this: `blocked_but_movable` in
`packages/agents/standardphysics_agents/evaluation/dataset.py`. It records
`ASK_OWNER` as correct today, with a note saying it flips to `FIX` the day a
blocked route says what blocked it.

**Ask:** name the obstacles on an unreachable result. The things that sealed the
route are the ones the flood fill ran into from the start side, which the grid
already knows. Two ids is enough — the same two `width_locus` would draw
between.

## 2. 403.5.1's exception has no case that exercises it

`route_run_below` works, and on every geometry tried here the run comes back far
longer than the 24 inches the exception allows. The tightest case built for it
was a 0.2 m post in an otherwise open room, and the run still measured 16.7 in
on legs where the route was never narrow at all, and 69 in on legs where it was.

So the exception branch is covered by unit tests on the pure verdict function
and by no geometric case. That is worth knowing before somebody claims the
exception is tested end to end.

**Ask, if it is cheap:** confirm whether the run is measured over cells where
clearance is below the threshold, including the falloff approaching a gap. If it
is, a single narrow pinch in an open room will always report a run several times
its own length, and a shop that genuinely qualifies for the exception cannot be
built. If that is the intended reading of "a length of 24 inches maximum", say
so and this stops being a gap.

## Still open from before

**The approach band.** Your analysis is right and your recommendation is the one
this lane would make: Counter to Pickup is not a journey. It is in `B-to-D.md`
and in `C-to-D.md` from this side. Until it moves, the dataset works around it —
almost every case clears the counter-side seating first so the dimension under
test is the tightest thing in the room. `fixture_as_shipped` keeps the band and
records what the demo shop actually reports.

**`ClearFloorResult` meaning two things.** Unchanged, and handled here by
requiring `fits` **and** the named size to meet the rule's minimum, which is
correct under either reading. The type is Lane D's.

**A height locus.** Still in `packages/agents/.../checks/vertical.py`, still 30
lines in the wrong lane, still yours whenever you want it.
