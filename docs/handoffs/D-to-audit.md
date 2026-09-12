# D to audit: A-6 and A-9 fields are approved

Brendan, Lane D's person, approved both fields as proposed in
`audit-to-D.md`. They land in the next Lane D push, with defaults that keep
today's behaviour.

- **A-6:** `Stop.anchor_node_id: UUID | None = None`. The fixture scenario
  anchors Entrance and Exit to the front wall, Counter and Pickup to the
  counter, and Seat to table_3.
- **A-9:** `WidthResult.needs_measurement: bool = False`.

Two things the audit may want to track:

- **Sealed doorways.** Walls seal their doorways in `occupancy.build_grid`.
  Reproduced at `28e64c1`: all 17 samples across the front door are occupied,
  and a stop 1 m outside the door cannot reach the counter. See `D-to-B.md`.
- **The Seat stop.** It sat at the centre of table_3, so leg 3 measured 6.89 in
  from inside a table. The fixture moves it into open floor.
