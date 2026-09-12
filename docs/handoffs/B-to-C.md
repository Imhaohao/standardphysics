# B to C: real measurements are ready

`PipelineMeasurements` implements `MeasurementProvider` against real geometry.
Swap the constructor argument and nothing else changes:

```python
from standardphysics_pipeline import PipelineMeasurements

measure = PipelineMeasurements()          # was FixtureMeasurements()
```

On the fixture shop it returns **exactly 31.0000 inches** for leg 0, names both
display cases as the blockers, and returns **exactly 36.0000** after the
documented 5 inch fix. It also gives you a drawable path and a pinch point for
the locus.

Two things worth knowing.

**Route width ignores the last 30 inches before each stop.** Standing at a
counter puts you within arm's reach of it, so the tightest point of any journey
is otherwise always its destination. Whether there is room to use the counter is
`counter_approach`, which measures the 48 by 30 inch clear floor space against
ADA 2010 305.3.

**The fixture counter is 43.3 inches tall.** ADA 2010 904.4.1 allows 36. That is
a second real finding waiting for you in the fixture, so you have both a route
check and a height check to build against without inventing data.

`turn_clear_width` currently delegates to `route_clear_width`. That is honest for
tier 1 and wrong for tier 2 — tell me when you need the real 180 degree turn
rule and I will build it.
