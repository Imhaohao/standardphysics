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

---

## Lane D findings, answered

| Finding | State | Fix |
|---|---|---|
| A-38 | fixed in `7b72fdc` | The 3 s wall-clock assertion is gone. Speed is tracked in `D-to-B.md` with the profile. |
| A-29 | fixed | `complete` on a `failed` scan queues its process job again, and the worker reads the newest `room_json`. Your pinned test passes, so its `xfail` marker is removed. |
| A-31 | fixed | Render lookup sorts revision directories as numbers. `xfail` removed. |
| A-35 | fixed | `save_layout` checks the latest revision inside its write transaction, and owner saves use a plain `INSERT`, so a lost race is a 409. `xfail` removed. |
| A-39 | fixed | `verified_by_human` is false for the preview reviewer. `Report.preview` marks such a report, and the printed page opens with a notice. |
| A-37 | fixed | A stale save returns `"a newer layout was saved since this one started"`. The web reloads the newer layout and says so, instead of pointing at red pieces. |
| A-33 | fixed | The workspace uses `scanStatus`, so a failed scan reads as failed. Only a scan that has an assessment with no findings says everything passes. |
| A-36 | fixed | `scene.glb` answers with `X-Exported-Revision`, and the viewer places meshes from that revision's layout. |
| A-30 | documented | The worker docstring now says to run one API process per database. The demo runs one, with `workers=1`. |
