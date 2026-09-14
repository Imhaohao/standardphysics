# How the app gets there

The plan behind [`MISSION.md`](MISSION.md). It names what exists, what it has
to become, and the order that keeps the tests green on the way.

## The two abstractions everything else hangs off

Both of the hard requirements collapse to the same shape of problem, and both
have the same answer.

**A rule is data, not a function.** Today `RuleSpec` carries a threshold and a
citation, and a hand-written function in `checks/` knows which surfaces to
measure for it. That is why there are eighteen rules. If a rule instead names a
*measurement primitive* and its arguments, one evaluator runs every rule, and
adding a provision means writing down what it requires.

**A question is a plan, not a kind.** Today `ask/query.py` parses into one of
eight kinds and dispatches to one of eight executors. If a model instead
composes a plan out of the same primitives, the code stops knowing what kinds
of question exist.

So the centre of the system is one library of typed primitives that read the
scene and take measurements. Rules compose them. Questions compose them. Adding
a primitive widens both at once.

```
                    ┌──────────────────────┐
   ADA provisions ──▶  primitive library   ◀── questions from the ask box
   (rules as data) │  scene reads +        │   (plans from a model)
                    │  measurements        │
                    └──────────┬───────────┘
                               │ every number, with provenance
                    ┌──────────▼───────────┐
                    │  the measured scene  │
                    └──────────────────────┘
```

## Phase 0 — Foundations

### 0.1 Two providers with a written policy

`models.py` sends every call to OpenRouter. Fireworks does not exist in the
codebase yet.

New `packages/agents/standardphysics_agents/providers/`:

| File | Holds |
|---|---|
| `protocol.py` | `Provider`: `structured(prompt, schema)`, `vision(images, prompt, schema)` |
| `fireworks.py` | Fireworks client, open-weights models |
| `openrouter.py` | the existing client, moved |
| `policy.py` | every workload, its provider, and the reason |

`policy.py` is the whole point: a named workload resolves to a provider, and
the reason is a string in the table rather than a decision someone made once.

| Workload | Provider | Why |
|---|---|---|
| `detect` | Fireworks | per-frame open-vocabulary detection, hundreds of calls per scan |
| `ocr` | Fireworks | reading text off surfaces, one call per candidate region |
| `label` | Fireworks | naming a carved box from a crop |
| `plan` | OpenRouter | composing a tool plan from an arbitrary question |
| `view` | OpenRouter | choosing how to present a result |
| `layout` | OpenRouter | proposing a rearrangement under constraints |

A new call site adds a row. A call that could run on open weights and does not
is a defect in the table, not a preference.

### 0.2 The harness that says whether any of this works

Ten people calling it immaculate is the bar, and the way to get there is to
measure before they do. `packages/agents/standardphysics_agents/evaluation/`
already runs sweeps; it gains two suites.

**Object recall.** For each scan in `datasets/phone`, a person lists every
object they can see. The suite scores what discovery found against that list.
The number to move is recall, not the count of boxes.

**Question suite.** Every question in `MISSION.md` plus many more, each with the
shape of a correct answer rather than an exact string: which nodes it must
reference, which primitives must appear in the plan, whether a number is
required. An answer that renders nothing scores zero.

## Phase 1 — The scene

### 1.1 A real tree

`SceneNode.parent_id` exists. `discovery/boxes.py:resting_parent` fills it one
level deep by testing whether a box floats above another box's top face, and
only for discovered objects.

Contract changes in `packages/contracts/standardphysics_contracts/scene.py`:

- `relation: Literal["rests_on", "inside", "mounted_on", "part_of"] | None`,
  so the edge says what kind of attachment it is. A blanket rests on a bed; a
  pen is inside a cup; a poster is mounted on a wall.
- `SceneGraph` validates the tree: every `parent_id` resolves, no cycles, and
  the chain ends at a floor or a wall.
- `SurfaceText`: what a surface says, where on it, and which frames read it.

Containment needs its own test. Support asks whether the underside of one box
sits within a tolerance of another's top face; containment asks whether a box
lies inside another's volume, which `boxes.contained_fraction` can already
measure and nothing calls for this purpose.

### 1.2 Discovery that finds everything

`discovery/discover.py` walks the capture once over evenly spread frames and
returns quietly when an input is missing. Three changes:

- **Frames by coverage, not by count.** Pick frames so every surface of the
  room is seen from somewhere, using the coverage the phone already records.
- **Text.** A pass that finds text regions and projects them onto the node
  whose surface they land on. This is what makes "what did it say on my
  whiteboard" answerable, and it is a capability the app does not have at all.
- **Loud failure.** A scan that cannot be discovered says so and marks the
  objects it could not name, rather than producing a room with holes in it.

### 1.3 An export that carries the tree

`blender_scripts/build_glb.py` flattens the graph. The GLB has to keep the
parent chain, so the model that reaches the browser is the scene, not a pile of
boxes at the same level.

## Phase 2 — Every provision

### 2.1 The primitive library

New `packages/pipeline/standardphysics_pipeline/primitives/`. Each primitive is
typed, takes the scene and named arguments, and returns a measurement carrying
what it measured and where, so a finding can always point at the thing.

A first set, drawn from what the standard actually asks about:

```
clear_width(path)                     height_above_floor(surface)
clear_floor_space(at, approach)       knee_and_toe_clearance(under)
turning_space(region)                 protrusion(node)
door_clear_width(door)                maneuvering_clearance(door, approach, side)
change_in_level(edge)                 running_slope(surface) / cross_slope(surface)
operable_part_height(node)            reach_depth(to, over)
```

`checks/` collapses into this. The measurement logic in `route_width.py`,
`turn_width.py`, `door_width.py` and the rest moves into primitives, and the
bespoke check files go.

### 2.2 A rule that names its measurement

The first draft of this plan had a rule name one primitive and a threshold.
Reading `checks/service_counter.py` showed that is too thin: real provisions
pick out elements, sometimes apply only under a condition, and only then
measure. 904.4.1 asks about counters; whether the point of sale sits on the
lowered section applies only when a lowered section exists.

So an expression has three parts, and `$element` is the node under
consideration:

```
select:     {primitive: "elements_of_role", arguments: {role: "sales_counter"}}
when:       {primitive: "has_lowered_section", arguments: {node_id: "$element"}}
measure:    {primitive: "height_of", arguments: {node_id: "$element"}}
comparison: at_most
threshold:  36
unit:       in
scope:      {space_types: ["public_accommodation"]}
```

`select` and `when` are primitives too, returning nodes and a truth, which is
why the vocabulary has those return types. One evaluator runs any rule with
this shape, and it refuses a measurement that answers in the wrong unit rather
than comparing square inches against a rule written in inches.

Provisions too tangled even for this keep a hand-written check, declared as
such on the rule. An escape hatch with a name is honest; a default is not. `scope` is what stops a dorm room
being told it fails a service-counter rule: Title III governs public
accommodations, a bedroom is not one, and a finding that does not apply is
worse than no finding.

Some provisions cannot be measured from a scan at all, such as braille on
signage or the audibility of an alarm. Those get a record saying so rather than
being silently absent, because the honest answer to "do you check everything" is
a list of what is checked, what is not, and why.

### 2.3 Getting the standard in

Authoring a few hundred provisions by hand is the job Phase 2 exists to make
possible. A model reads a section and proposes the record; the threshold is
then confirmed against the source text by the same mechanism
`scripts/verify_rulepack.py` already uses, so no number reaches a shop owner
without having been checked against the sentence it came from.

Coverage becomes a number: provisions in the standard, provisions expressed,
provisions measurable from a scan.

## Phase 3 — The ask box that knows nothing

Four stages, none of which contains the word "pen" or "whiteboard".

```
question ─▶ plan ─▶ execute ─▶ compose view ─▶ verify ─▶ render
             │         │            │            │
          model     code only     model        code only
```

**Plan.** The model gets the question, a summary of the scene, and the schemas
of every primitive. It emits a sequence of calls. Unknown primitive or unknown
node id is a rejection before anything runs.

**Execute.** Code runs the plan against the real scene. Every result carries
provenance. The model has supplied no numbers and cannot.

**Compose.** The model gets the results back and emits a view built from
generic display primitives, none of which is tied to a kind of question:

| Primitive | Shows |
|---|---|
| `highlight` | named nodes, with a camera that frames them |
| `measurement` | a span between two points, with its number |
| `table` | rows drawn from results |
| `annotation` | text anchored to a node |
| `layout_diff` | the same room before and after a set of moves |
| `prose` | a sentence, when a sentence is genuinely the answer |

"Are all of the pens in my dorm room?" resolves to a highlight over the nodes
whose parent chain reaches the room, plus a count. "What did it say on my
whiteboard?" resolves to an annotation carrying the `SurfaceText` read off that
node. "How could I arrange this room if another roommate moved in?" resolves to
a `layout_diff`. None of those three mappings is written down anywhere; they
fall out of the primitives.

**Verify.** Before anything renders, code checks that every node id exists, that
every number traces to a primitive result rather than to the model, that the
view has content, and that what it claims matches what was returned. A failure
re-plans once with the reason attached. A second failure says what it tried and
could not do. An empty screen is a bug, never an outcome.

### What gets deleted

`ask/query.py` and the eight executors (`dimensions`, `inventory`, `places`,
`shapes`, `space`, `spans`, `standards`, `layout`) go, along with `subjects.py`
and the closed `QueryKind` set. Their measurement logic moves into primitives
first, so the deletion never crosses a green test run.

## Phase 4 — The ten-user bar

- Blender in the image, because an uploaded scan currently renders as grey
  boxes and a report with no pictures.
- The open audit findings in `PROGRESS.md`, starting with A-14 and A-15, which
  are why `turn_clear_width` is switched off.
- Every scan in `datasets/phone` through the whole path, end to end, with the
  object-recall and question suites run against the result.
- Ten people, their own rooms, and what they say.

## Order of work

Phase 0 first, because the policy table and the harness are what make the rest
measurable. Then Phase 1, because rules and questions both read the scene and a
scene with no tree limits both. Then Phase 2 and Phase 3 in parallel: they
share the primitive library, and once it exists they do not block each other.
Phase 4 runs throughout rather than at the end.
