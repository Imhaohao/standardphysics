# ARIA

ARIA is CoreWeave's research agent inside Weights & Biases. It reads the runs in
a project — the config each run was launched with, the metrics it logged, the
tables behind it — and answers questions about them in panels and reports. It
will also design the next experiment and say what it expects to see.

So the work on our side is to put the evaluation in the project in the form
ARIA reads: one run per configuration, flat hyperparameters in the config,
every score and every cost as a metric, and the per-case results in a table
behind each run.

`python -m standardphysics_agents.cli experiments` does that.

## What a run holds

One run is one configuration of the shop review, scored against all 39 labelled
cases from `packages/agents/standardphysics_agents/evaluation/dataset.py`.

**Config.** Every knob that changes what the system does without changing what
a correct answer is.

| Field | What it sets |
|---|---|
| `cell_size` | The occupancy grid every width and clearance is measured on, in metres. The pipeline ships 0.025. |
| `fix_candidates` | How many arrangements the fix agent measures before it gives up. |
| `measurements` | `pipeline` for Lane B's real geometry, `stub` for the fixtures' simplified stand-in. |
| `router` | `typesafe` for the router, `local` for the labelled policy behind it. |
| `run_fixes` | Whether the fix agent runs at all. |
| `preview_unverified` | Whether the run treated the rule pack as verified. A run with this on is not evidence about a shop. |
| `rulepack_version`, `cases` | Which rules and how many cases produced the numbers. |

**Metrics.** The seven scorers keep the names `scorers.py` gives them, so a
metric means the same thing here and in Weave's Evals tab. `measurement_error_in`
is an error and lower is better; the other six are shares of the cases.

Cost sits under `cost/`. `cost/measurements_taken` is the one to compare across
configurations: it counts every measurement the run asked for, which is the same
number every time, where `cost/wall_seconds` moves with the machine. Each
measurement in the provider gets its own tally under `measurements/`, so a run
says which question it spent its time on.

**The case table.** One row per case: what the checks reported, what the case
expected, which action the router chose, whether the fix held, and every score.
This is what ARIA reads to get from a mean back to the cases behind it.

## Running the grid

```bash
python -m standardphysics_agents.cli experiments              # the default grid
python -m standardphysics_agents.cli experiments --dry-run    # name the configurations
python -m standardphysics_agents.cli experiments --cases 5    # a quick look
```

The default grid crosses three cell sizes with three ladder depths, which is
nine runs and about three minutes. The grid saves to `runs/experiments.json`
first and uploads second, so a missing key costs the upload rather than the
numbers.

`WANDB_API_KEY`, `WANDB_ENTITY` and `WANDB_PROJECT` from `.env` decide where the
runs land. It is the same project Weave traces into, so the traces and the
experiments sit together.

Every check is off until a person has read its section and confirmed its number,
and a grid with no checks enabled scores nothing. `--preview-unverified` scores
as if every rule had been read, which is how the numbers below were produced,
and it records that in the config.

## What a person has to set up

| What | Why an agent can't |
|---|---|
| The W&B project is a team project, not a personal one | ARIA only works in team projects |
| An org admin turns on **Smart features** under Settings, Privacy | Account access |
| `WANDB_API_KEY`, `WANDB_ENTITY`, `WANDB_PROJECT` in `.env` on the demo machine | Account access |

ARIA needs W&B Multi-tenant Cloud. Open it with **Ask ARIA** at the top right of
the project.

## Questions to ask it

These are written against the metrics above, because a question naming a real
field gets an answer with a panel behind it.

1. Group the runs tagged `shop-review` by `cell_size` and `fix_candidates`. Which
   field moves `finding_precision`, and which one only moves cost?
2. `finding_precision` is 1.0000 at `cell_size` 0.025 and 0.9653 at both 0.015
   and 0.05. Open the `cases` table on those runs and tell me which check and
   which cases account for the difference.
3. Plot `cost/measurements_taken` and `cost/wall_seconds` against `cell_size`.
   What is the cheapest cell size that holds every score at 1.000?
4. Does `fix_candidates` change any metric at all? Show the evidence either way.
5. Which measurement under `measurements/` is asked for most, and how does that
   change with `cell_size`?
6. Propose the next configuration to run and say what you expect it to show.

A W&B automation can send one of these on its own: point it at a run finishing
in this project and ARIA starts the conversation. That needs the same account
access as the rest.

## What the grid says already

Nine runs, 39 cases each, rules scored as verified, on an M2 Pro.

| Cell size | Weakest score | Measurements | Seconds |
|---|---|---|---|
| 15 mm | 0.9653 `finding_precision` | 4,878 | 51.7 |
| 25 mm | 1.0000 | 4,732 | 16.8 |
| 50 mm | 0.9653 `finding_precision` | 4,345 | 4.0 |

Ladder depth sits at 4, 8 and 16 in every row, and every row is identical:
the same scores, the same 13 candidates measured, the same seconds. The fix
agent never reaches its fifth candidate on this dataset, so the depth beyond
four is not doing anything the evaluation can see.

The cell size row is the one to look at. 25 mm scores 1.0000 and both
neighbours drop to 0.9653, which is the same two cases in both directions:
`lawsuit_counter` and `door_clearance_blocked` report a `turn_clear_width`
problem the labels do not expect. Reading the measurement behind it:

| Cell size | `lawsuit_counter` | `door_clearance_blocked` |
|---|---|---|
| 15 mm | 30.7 in | 40.2 in |
| 20 mm | 26.8 in | 40.9 in |
| 25 mm | nothing reported | nothing reported |
| 30 mm | 30.7 in | nothing reported |
| 50 mm | 33.6 in | 43.3 in |

403.5.2 asks for 48 inches at the turn, so every number there is a shortfall.
The shipped cell size is the only one of the five that finds no 180 degree turn
on these two shops at all. That points at turn detection rather than at the
threshold: the turn is recognised from the path the widest-path search returns,
and that path changes with the grid. Lane C's `needs_human` already carries the
approximation this rests on — geometric turn detection at about 122 degrees.

Two things follow, and neither is an agent's to decide. Whether those two shops
contain a 180 degree turn is a question for Lane B and the person holding the
rule pack. Whether the labels or the check are right decides which one changes.

## The improvement we ship

The prize asks for one improvement ARIA found, shipped. Fill this in from the
ARIA session with the question that produced it, the change, the commit, and the
grid before and after.
