# How the app gets there

The plan behind [`MISSION.md`](MISSION.md).

## The mistake this plan corrects

The first version of this document said the centre of the system was a library
of named primitives: `objects_on`, `text_on`, `height_of`. Rules would compose
them and so would questions, and that was supposed to be emergent.

It is not. It moves the closed set down one level and leaves it there.

`rests_on` is an ontological claim, not a measurement. So is `inside`. So is
the `NodeKind` enum of wall, door, window, opening, floor and object, which 68
places in this repository branch on today. A room full of things those words
fit works. A room full of things they do not fit fails exactly the way the
eight question kinds failed, and for the same reason: somebody decided in
advance what kinds of thing exist.

The test is not a dorm room. It is a place where the objects have no names we
know, standing in relations we have no words for, under physics we did not
assume. Nothing in the system may depend on the world being a room on Earth.

## What is actually fixed, and what must not be

The way out is to notice that two very different things were being mixed
together.

**Geometry is universal.** That the volume of one measured region lying inside
another's hull is 0.97, or that the signed gap between two surfaces along the
measured gravity vector is two millimetres, is true on any planet. It carries
no claim about what either thing is.

**Ontology is not.** That the first thing is "inside" the second, or that it is
a "pen", or that the gap means it "rests on" it, is interpretation. It belongs
to a world, and it has to be produced from evidence rather than declared in a
`Literal`.

So the system has three layers, and only the bottom one is closed.

```
  ┌───────────────────────────────────────────────────────────┐
  │ 3  Composition    a question arrives, and an expression    │
  │                   is written to answer it. New predicates  │
  │                   are authored here, not looked up.        │
  ├───────────────────────────────────────────────────────────┤
  │ 2  Interpretation entities and relations, coined from      │
  │                   evidence and stored as data. Open.       │
  │                   Every one carries the geometry that      │
  │                   justifies it.                            │
  ├───────────────────────────────────────────────────────────┤
  │ 1  Substrate      measured regions and the operators over  │
  │                   them. Closed, mathematical, nameless.    │
  └───────────────────────────────────────────────────────────┘
```

The one rule from the old plan that survives untouched: **the model supplies
structure, the engine supplies values.** A model may say which regions to
compare and how; it may never say what the comparison returned.

## Layer 1 — Substrate

What the scan measured, before anything is named. Not objects: regions. A
region is a spatially coherent piece of the measured field with an id and
nothing else asserted about it.

The operators over regions are the closed set, and they are closed because
mathematics is:

```
regions()                      every measured region
hull(r) / bounds(r) / volume(r) / area(r) / centroid(r)
principal_axes(r)              the directions the region actually extends along
overlap_fraction(a, b)         how much of a lies within b
gap(a, b, along)               signed distance between surfaces in a direction
relative_offset(a, b)          one region's pose in the other's frame
adjacency(a, b)                do their surfaces meet, and over what area
free_space(from, to)           the widths a body could pass through
gravity()                      the direction the phone measured, not an assumption
frames_seeing(r)               which captures observed this region
image_of(r, frame)             the pixels
markings_on(r)                 glyphs found on a surface, and what they read as
```

Nothing there says wall, floor, counter or up. `gravity()` returns a measured
vector because the phone has an IMU, not because down is a concept the code
believes in; a scan taken where that reading is meaningless returns a region
field the rest of the system can still work over.

`markings_on` is the closest call. Reading glyphs is nearly ontology. It stays
in the substrate because what it asserts is only that this surface carries
these marks and here is the image they came from, which is a measurement.
Whether the marks are a whiteboard's homework or a warning in a language nobody
has seen is layer 2's problem.

## Layer 2 — Interpretation

A model reads the substrate and coins what it finds. Two things it produces,
both stored as data:

**Entities.** A region, a name the model chose, and its confidence. The name is
a free string. There is no enum, so nothing prevents "bed", "whiteboard", or a
word invented on the spot for a thing with no earthly equivalent.

**Relations.** A named edge between two entities, with the geometric predicate
that justifies it attached:

```
{ "name": "rests on",
  "from": "region-12", "to": "region-7",
  "because": {
    "all": [
      {"op": "gap", "a": "$from", "b": "$to", "along": "gravity", "under": 0.005},
      {"op": "overlap_fraction", "a": "footprint($from)", "b": "footprint($to)", "over": 0.5}
    ]
  },
  "confidence": 0.94 }
```

`rests on` is a string the model coined for this scan, and `because` is a
substrate expression the engine can re-run. That is the whole difference from
what I built: the relation is discovered and justified rather than declared in
a `Literal`, so a scan of somewhere strange produces relations with names we do
not have and predicates we did not anticipate, and every layer above carries
them without change.

Relations that recur get cached, which is why a dorm room still ends up with
something very like `rests_on` everywhere. It was found, not assumed.

**Nothing above this layer may branch on a name.** A name is for showing a
person. Code that needs to know whether one thing is on another re-runs the
predicate.

## Layer 3 — Composition

A question arrives. The model is given the substrate operators, the entities
and relations this scan produced, and an expression language whose atoms are
those operators.

It writes an expression. The engine evaluates it against real geometry.

The important part is that the model can **author a predicate nobody
anticipated**. Asked which things are precariously balanced, it does not need a
`precariously_balanced` primitive to exist. It composes one: the supported
region's centroid projects outside the supporting region's footprint by some
fraction, and the contact area is small relative to the mass above it. That
expression is evaluated, not believed.

That is what "emergent" has to mean. Not a rich menu of primitives, but the
ability to write a predicate that was never on any menu.

The expression language is small and total. Map, filter, reduce, compare,
arithmetic, and the substrate operators as atoms. It cannot loop unboundedly,
open a file or reach the network. A model writing an expression can therefore
be given a lot of freedom safely, because the worst an expression can do is
return the wrong answer, which the next stage catches.

**Presentation is composed the same way.** A view is an expression producing
geometry to highlight, spans to measure, rows to tabulate, or a rearrangement
to show. There is no list of question types with a renderer each.

**Verification is separate and adversarial.** Before anything renders, a
different pass checks that every entity referenced exists in this scan, that
every number in the answer came from an evaluated expression rather than from
the model's text, and that the view is non-empty. A failure re-plans once with
the reason attached. A second failure says what was tried and what could not be
established. An empty screen is a bug; a confident wrong answer is worse.

## What this means for the rules

ADA is a domain pack, not the engine. Its provisions select elements by
predicate over interpreted entities rather than by a role enum, and the pack
declares the world it assumes. The engine that runs it has nothing in it about
counters or doorways, which is what lets the same engine carry a different
standard, or none.

The select / when / measure expression already built is the right shape. What
has to change is that its steps become substrate expressions rather than calls
to named semantic primitives.

## What has to be undone

Written down plainly, because I built some of it last night:

| Built | Why it has to change |
|---|---|
| `Relation` as a four-member `Literal` | becomes a free string with an attached predicate |
| `NodeKind` as a six-member `Literal`, and the 68 places that branch on it | becomes a coined name nothing branches on |
| `objects_on`, `objects_inside`, `text_on`, `what_carries` | become substrate expressions, composed rather than called |
| `find_objects` matching on label words | becomes selection by predicate, with names for display only |

What survives, because none of it assumed a world: the tree walk over whatever
edges exist, evidence and provenance on every result, fail-closed calling, the
refusal to compare across units, and the select / when / measure evaluator.

## Order of work

1. **Substrate first.** Region segmentation and the operator set, with the
   operators tested against geometry rather than against a room.
2. **Interpretation.** The coining pass, and the predicate store. A relation
   nobody wrote down in advance has to survive a round trip.
3. **Composition.** The expression language, the planner, the view composer,
   the verifier.
4. **Rules as a pack** over layers 1 and 2, with ADA as the first pack.
5. **Proof**, described below, running throughout rather than at the end.

## How this gets proved

A checklist of files deleted and greps returning nothing is something to game.
The proof has to be empirical and held out.

**A generated suite.** A model is shown a scanned scene and writes eighty
questions a person might really ask about it, under a hard diversity
constraint: no two may be answerable by the same approach. One counts things.
One asks what some surface says. One asks how to rearrange a space for another
occupant. One asks something nobody anticipated.

**Held out.** The questions are generated against scenes the implementation was
not developed on, and are regenerated for each run, so they cannot be memorised
or special-cased.

**Graded against the scene, not against a string.** A judge sees the question,
the answer, the view and the real scene data, and scores whether it was
answered, whether every number traces to an evaluated expression, and whether
the view shows something.

**Some questions have no answer.** Around one in eight is unanswerable from the
scan. Saying so is a pass. Producing a confident answer anyway is a failure,
which is the part a system that games the suite fails hardest.

**The scrambled run.** The same suite runs against a copy of the scene with
every coined name replaced by a nonsense token. Structural questions must score
the same. Any drop is something keyed to English names for earthly objects, and
names the exact defect this whole plan exists to remove.
