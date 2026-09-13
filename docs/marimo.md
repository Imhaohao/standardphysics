# marimo

marimo is a reactive Python notebook. A cell is a function, marimo reads which
names each one uses, and changing a value re-runs only the cells downstream of
it. There is no hidden state and no stale output, so a notebook checked into a
repository runs the same way for the next person who opens it.

`notebooks/scenario_sweep.py` uses that to make the review interactive. Sliders
set the shop's dimensions, and the same evaluator that scores the labelled
dataset reads the room they build.

```bash
./start.sh                                     # once, to install
.venv/bin/marimo edit notebooks/scenario_sweep.py
```

`marimo edit` opens it with the code visible. `marimo run` serves the same
notebook as an app with the code hidden, which is the version to put on screen.

## The knobs

| Slider | What it moves |
|---|---|
| Gap between the display cases | Rebuilds both cases so the aisle between them is the width you set, without pushing either one through a wall |
| Counter height | The ordering counter, which 904.4.1 holds to 36 in |
| Front door opening | The clear width of the front doorway |
| Keep the seating by the counter | Whether the tables that crowd the counter are in the room |
| Routine | Ordering a drink from inside the door, or walking in from the street |

The routine matters more than it looks. Ordering a drink starts inside the shop,
so the aisle is the tightest thing on the route. Walking in from the street puts
the doorway on the route, and then widening the aisle does nothing — the chart
shows the route failing across the whole range, because the door is the pinch.

## Nothing here is a second implementation

`packages/agents/standardphysics_agents/evaluation/scenarios.py` turns the
knobs into a `Case` and hands it to `run_case`, the same function the Weave
evaluation and the W&B experiment grid call. The notebook draws findings and
reads scorers; it never measures anything itself and it never decides what
passes. A finding that appears while you drag a slider is the finding the
server would report for that room.

That is also why the headline figure is a measurement error. A knob that sets a
dimension is a claim about what a correct measurement of it would be: set the
aisle to 31 in and a route starting inside the door should come back at 31 in.
`measurement_error_in` reads the two against each other, and on every setting
tested it lands inside a rounding error.

Where a knob stops pinning a dimension it claims nothing, and the notebook
shows less rather than guessing. With the street routine the aisle carries no
expected route measurement, and the cited reference line is not drawn, because
crossing 36 in on an aisle axis would not change what the route reports.

## What the sweep chart says

One row per check, and its bar covers the settings where that check reported a
problem. Rows that change their mind come first; a check that is wrong at every
setting comes next; checks that pass throughout are demoted.

A verdict is only known at the settings the sweep visited, so a change is drawn
at the midpoint between the two readings that bracket it. Fewer readings is a
coarser boundary, not a wrong one. The solid reference line is separate: it
comes from the finding's own `required_inches`, so it sits where the standard
puts it rather than where a reading happened to fall. Watching the sampled
boundary land on that line is the point of the chart.

`Readings across the range` is the cost control. Thirteen readings of the
shipped shop take about four seconds. Moving the swept slider itself does not
pay that again: the sweep replaces that knob at every reading, so its current
value cannot change the answer, and the notebook parks it before asking the
cache. Only the marker moves.

## Rules a person has to read first

A check runs when somebody has read its section and typed the number back.
Nothing is verified in a fresh clone, so the notebook offers to read every rule
as verified and says plainly that it has. Numbers produced that way are for
development. `standardphysics-agents rules review --by "<name>"` is where a
real reader is recorded.
