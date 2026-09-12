# Audit to D: two contract fields the measurements need

Both come from findings in `PROGRESS.md`. Each is an optional field whose default keeps today's behaviour for every existing caller. Nothing in `packages/contracts/` has been edited; the protocol leaves that to you and your person.

## A-6: a stop needs to say which fixture it is at

Route width ignores everything within 0.75 m of each stop, so a counter does not set its own route's bottleneck. That also hides a 20 in gap 0.2 m inside the entrance, which reports 31 in.

The pipeline cannot tell a stop's own fixture from an obstruction beside it, because `Stop` holds only a name and a position.

**Proposal:** `Stop.anchor_node_id: UUID | None = None`. Route width then ignores only that node near the stop, and a stop with no anchor gets no exemption. The fixture scenario would anchor Counter and Pickup to the counter, Seat to its table, and Entrance and Exit to the front wall.

## A-9: a width needs a way to ask for a measurement

`door_clear_width` returns the door leaf. ADA 2010 404.2.3 measures from the door face to the stop with the door open 90 degrees, which a scan does not capture. Today a door with a 32 in leaf passes.

**Proposal:** `WidthResult.needs_measurement: bool = False`. `door_clear_width` sets it, and Lane C turns the result into a question with a photo request instead of a pass.

Both landed in `b5306c8`.

---

## The API in `a260626`

The upload contract matches what Lane A's app sends: paths, both headers, snake_case bodies, artifact IDs and kinds, the coverage dictionary, and 200 or 201 on upload. `services/api/tests` passes, 23 of 23. Three findings, details and repros in `PROGRESS.md`:

- **A-29, medium.** A scan that fails processing stays `failed` for good. The app's "Try the upload again" re-sends the same IDs, which return 200, and `complete` ignores anything not `uploading`. A corrected `room.json` gets 409 under the same ID, and under a new ID the worker would still read the oldest one. Pinned as a strict expected failure in `tests/test_audit_open_findings.py` using the new ID path. If you choose a different recovery design, replace that test with one for your design and delete the marker.
- **A-30, low.** `Worker.start` requeues every `running` job, so a second API process on the same database runs the first one's jobs again. That contradicts the docstring in `worker.py`.
- **A-31, low, not reachable yet.** The render route sorts revision directories as strings, so `9` beats `10`. It bites once an edit endpoint creates revisions.

## The viewer in `2fad000`

- **A-33, low.** `Workspace.tsx` says "Checking your shop" for any scan with a scene and no findings that is not `ready`, so a `failed` scan looks in progress forever. A `ready` scan with no findings says "Findings show up here once the shop is checked", while the shops page says "Everything we checked passes". Using `scanStatus` in the workspace would make the two agree.

## Rearranging in `a9ce65c`

- **A-35, medium, pinned.** `save_layout` checks the base revision outside its write transaction and inserts with `INSERT OR IGNORE`, so a save that loses a race to another save on the same base returns 201 while its layout is dropped. Reproduced at `9be20af`; details in `PROGRESS.md`. Checking the latest revision inside the transaction and treating an ignored insert as a 409 would fix it.
- **A-31 is now reachable, pinned.** Saved layouts pass revision 9, and after eleven saves on the sample shop the render route serves revision 9's image for a revision 11 assessment. Sorting the revision directories as numbers fixes it.

## Dragging in `945b8a4`

The browser's `moveNode` matches Lane C's `move_node`, pointer deltas reach the floor with the right sign, and stale check answers are dropped by sequence.

- **A-37, low.** A 409 for a stale base shows "Check the pieces marked in red" with nothing red, and with no refresh every retry sends the same stale base. Reading the `error` body and refreshing the scene on a stale base fixes both.
- **A-36, low.** The viewer treats revision 0 as the layout the GLB came from. If the first GLB is a box export from a later revision, which happens when revision 0 exported nothing, its boxes are moved twice. Recording which revision a GLB was exported from would close it.
