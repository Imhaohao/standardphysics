# B to C: master is green, and the fix was mine to make

`turn_detail` returning `None` zones broke `turn_width.py:69`, which compares
each zone with `<`. That is my fault twice over: I changed a return type Lane C
consumes, and I only ran `tests/` before pushing, which never touches your
checks. Master was red on `0f0e01b`. It is green now — 141, 134 and 23 across
the three suites.

## What changed, and why it is in my lane and not yours

`turn_detail` now returns `None` when a turn could not be fully measured,
instead of handing you a `Turn` with a missing zone. A caller comparing three
widths against thresholds cannot do anything sensible with a missing one, and
giving you a `None` to trip over is worse than saying there is no turn here to
assess. Your code needs no change.

The partial turn is still there when you want it:

```python
turn = measure.turn_detail(graph, scenario, leg, require_measured=False)
turn.fully_measured      # False
turn.approach_inches     # None — the zone ran off the end of the route
```

**Worth opting into eventually.** Right now a turn we could not measure is
silently absent from the report. It would be better as a question — "we could
not see enough of the turn by the display case, send us a photo" — which is
what `require_measured=False` plus `fully_measured` is for. Your call when.

## Why it happened, so it does not again

I have added the full three-suite command to `packages/pipeline/README.md` and
I am running it before every push from now on. `pytest` alone passes while your
lane is broken, because nothing in `tests/` imports your checks.

The deeper point: this lane's return types are your interface. I treated
"Optional is more honest" as a local improvement when it was a breaking change
to a consumer. Next time I will put it in a handoff before pushing it.
