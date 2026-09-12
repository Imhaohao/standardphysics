# B to C: measurements and loci are ready

`PipelineMeasurements` implements `MeasurementProvider` against real geometry.
Swap the constructor argument and nothing else changes:

```python
from standardphysics_pipeline import PipelineMeasurements
measure = PipelineMeasurements()          # was FixtureMeasurements()
```

On the fixture shop leg 0 returns **exactly 31.0000 inches**, names both display
cases as the blockers, and returns **exactly 36.0000** after the documented
5 inch fix.

## Attaching a finding to the model

You do not have to work out camera angles. Hand a result to `width_locus` and
attach what comes back:

```python
from standardphysics_pipeline import width_locus

result = measure.route_clear_width(graph, scenario, 0)
finding = Finding(
    ...,
    measured_inches=result.inches,
    required_inches=36.0,
    locus=width_locus(graph, result),
)
```

The locus carries a dimension line drawn between the two facing surfaces, a
label already formatted as `31 in`, both blocking node IDs for highlighting, and
a camera placed on the side the customer approaches from, pitched down 38
degrees and pulled back to frame the gap.

`region_locus(clear_floor_result, node_ids)` does the same for turning space and
clear floor space. `path_locus(result)` gives the whole route for before and
after replay.

## Two findings live in the fixture

**Route width.** Leg 0 measures 31 in against the 36 in that ADA 2010 403.5.1
requires.

**Counter height.** The fixture counter is 43.3 in. ADA 2010 904.4.1 allows 36.
`measure.counter_height(graph, counter_id)` returns it with the node and the
point it was measured at.

So you can build both a width check and a height check without inventing data.

## One thing that is honestly incomplete

`turn_clear_width` currently delegates to `route_clear_width`. That is fine for
tier 1 and wrong for tier 2 — say the word and I will build the real 180 degree
rule from 403.5.2.
