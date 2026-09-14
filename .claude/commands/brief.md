---
description: The standing brief for Standard Physics. Read before planning any work.
---

Read `docs/MISSION.md` and `docs/ARCHITECTURE.md` before you plan anything.

This is the brief every agent working on this repository builds against. It is
not a completion condition: `/goal` is the built-in that carries one of those.

The target is not a demo and not a prize. Standard Physics runs in production,
ten people scan their own rooms with it, and every one of them says it is
immaculate and does everything it is supposed to do. Work that does not move
toward that is not worth doing.

Four things have to be true:

1. **Every ADA provision is checked**, not the eighteen we hand-wrote. A rule
   is data naming a measurement primitive, so adding a provision means writing
   down what it requires. A rule that does not apply to this kind of room does
   not run.
2. **Every object in a scan is identified**, named, measured and placed,
   including the text written on it.
3. **The scene is a real 3D model** with a real tree. The blanket rests on the
   bed, the bed rests on the floor, the pens are inside the cup.
4. **Any question is answerable.** A model plans the answer out of primitives
   and composes the view out of generic display pieces. No question kind, no
   intent, and no subject appears in the source. Nothing renders until code has
   verified it references real nodes and carries real data.

Two rules that never bend:

- **The model never supplies a number about the room.** Judgment comes from the
  model, measurements come from the scene and the measurement provider.
- **Nothing reaches the screen unverified.** An empty screen is a bug, not an
  outcome.

Providers: Fireworks with open weights for volume work (detection, OCR,
labelling), OpenRouter for frontier reasoning (planning, view composition,
layout). A call goes to OpenRouter only when open weights cannot do it, and the
reason lives in `providers/policy.py`.

The existing app cuts corners everywhere. Restructure it rather than extending
it, and delete what is in the way.

$ARGUMENTS

## Proving work is done

`/goal` judges a condition from what lands in the conversation, not by reading
files itself. So every claim has to be shown, not asserted:

- Run `.venv/bin/python -m pytest -q` and `.venv/bin/python -m ruff check .`
  and let the output land in the transcript.
- For web work, run `npm run lint`, `npm run typecheck` and `npm run test` in
  `apps/web`.
- When a claim is about code that no longer exists, show the `grep` that comes
  back empty.
- When a claim is about behaviour, add a test that fails before the change and
  passes after, and show both runs.

Never weaken, skip or delete a test to make a check pass.
