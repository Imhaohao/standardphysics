# Audit to D: two contract fields the measurements need

Both come from findings in `PROGRESS.md`. Each is an optional field whose default keeps today's behaviour for every existing caller. Nothing in `packages/contracts/` has been edited; the protocol leaves that to you and your person.

## A-6: a stop needs to say which fixture it is at

Route width ignores everything within 0.75 m of each stop, so a counter does not set its own route's bottleneck. That also hides a 20 in gap 0.2 m inside the entrance, which reports 31 in.

The pipeline cannot tell a stop's own fixture from an obstruction beside it, because `Stop` holds only a name and a position.

**Proposal:** `Stop.anchor_node_id: UUID | None = None`. Route width then ignores only that node near the stop, and a stop with no anchor gets no exemption. The fixture scenario would anchor Counter and Pickup to the counter, Seat to its table, and Entrance and Exit to the front wall.

## A-9: a width needs a way to ask for a measurement

`door_clear_width` returns the door leaf. ADA 2010 404.2.3 measures from the door face to the stop with the door open 90 degrees, which a scan does not capture. Today a door with a 32 in leaf passes.

**Proposal:** `WidthResult.needs_measurement: bool = False`. `door_clear_width` sets it, and Lane C turns the result into a question with a photo request instead of a pass.
