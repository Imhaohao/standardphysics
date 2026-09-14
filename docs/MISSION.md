# Mission

## What production ready means here

It does not mean a demo survives a walkthrough, and it does not mean a judge is
impressed. It means the app runs in production, ten people use it on their own
rooms, and every one of them says it is immaculate and does everything it is
supposed to do. Until ten real users say that, this is not finished.

That bar rules out most of what the repository currently does. The app was
built to be demonstrated: the sample shop carries a committed model, several
stages degrade quietly when an input is missing, and the parts a demo never
reaches were never made to work. Every one of those shortcuts is now a defect.

## What the app has to do

### 1. Check every ADA provision, not eighteen of them

The rule pack holds eighteen rules. Each one needs a hand-written check in
`packages/agents/standardphysics_agents/checks/` that knows which surfaces to
measure and how, so the pack grows one Python function at a time. The 2010
Standards run to several hundred provisions, and writing a function per
provision is not a plan.

A rule has to become data expressed in a vocabulary of measurements the engine
already knows how to take. Adding a provision then means writing down what it
requires, not writing code. Coverage is measured against the published standard
rather than against the list of rules we happen to have.

The engine also has to know which rules apply to the room in front of it. Title
III governs public accommodations; a dorm room is not one, and telling a
student their bedroom violates a service-counter rule is worse than saying
nothing. Applicability is part of the rule, not an assumption baked into the
pipeline.

### 2. Identify every object in a scan

RoomPlan boxes the furniture categories Apple ships. Everything else in a real
room arrives as raw LiDAR with no name: the pens, the kettle, the whiteboard,
the laptop, the poster on the wall. `packages/pipeline/standardphysics_pipeline/discovery/`
already finds some of them from the photos, and it runs once, over a handful of
frames, and gives up quietly when an input is missing.

Every object a person would point at has to come back named, measured and
placed. That includes what is written on things: asking what the whiteboard said
means the text on its surface was read and kept.

### 3. Build a real 3D model of whatever was scanned

Scan a dorm room and the result should read like a Blender scene of that room.
The blanket is a separate object from the bed. The bed is a separate object
from the floor. The blanket rests on the bed, the bed rests on the floor, and
the model knows that chain.

Today `SceneNode.parent_id` exists and `discovery.boxes.resting_parent` fills it
one level deep, for discovered objects, by testing whether one box floats above
another's top face. Containment is not modelled at all, so pens in a cup on a
desk are three unrelated boxes. The scene has to carry a real tree, support and
containment both, and the exported model has to carry it too.

### 4. Answer anything, and show the answer

These are the questions, verbatim, that the app has to handle:

- Are all of the pens in my dorm room?
- What did it say on my whiteboard?
- How could I arrange this room if I had another roommate move in?

`ask/` today parses a question into one of eight kinds and hands it to one of
eight executors. Anything outside that set is rejected. None of the three
questions above is in the set, and adding them as a ninth, tenth and eleventh
kind is the same mistake as writing a check per ADA provision.

The code must not know what kinds of questions exist. A model reads the
question, composes an answer out of primitives that can read the scene and take
measurements, and chooses how to present it out of generic display primitives.
Nothing about pens, whiteboards or roommates appears anywhere in the source.

Two constraints hold that together:

**The model never supplies a number about the room.** This split already exists
in `ask/query.py` and it is the best idea in the codebase. Working out that "how
tall is my desk" is a question about height is judgment, and a model is good at
it. Knowing the desk is 29.5 inches is measurement, and a model is not. Every
number in every answer is read off the scene or taken by the measurement
provider.

**Nothing reaches the screen unverified.** Before an answer renders, the system
checks that it references nodes that exist, that it carries data, and that what
it claims matches what the primitives returned. A question that cannot be
answered says so. Nobody ever looks at an empty screen.

## Model providers

Two, with a policy rather than a habit. Fireworks runs open-source models and
takes the high-volume work: per-frame detection, OCR, captioning, embeddings,
classification. OpenRouter takes the frontier work that open weights cannot do
well: planning an answer, composing a view, proposing a layout.

A call goes to OpenRouter only when an open-source model on Fireworks cannot do
the job. That decision is written down per call site, not left to whoever is
editing.

## What this requires

The existing app takes many shortcuts. Meeting this bar means restructuring it
rather than extending it, and some of what is there now gets deleted. That is
expected and is not a reason to soften any of the four requirements.
