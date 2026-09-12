# B to A: I need one real room.json, early

The ingest parser is written against Apple's **documented** shape, not against
a real export. It is the only part of Lane B that is guessing, and it is
guessing about something only you can settle.

## What I need

One `room.json` from any scan — your desk, a corridor, thirty seconds of
anything. Commit it to `packages/fixtures/standardphysics_fixtures/data/real/`.
It does not need to be a shop and it does not need to be good. I need to see
the actual bytes.

Send it the moment the first export succeeds, ahead of the upload flow. If
uploading is not working yet, AirDrop it and commit it by hand.

## What I am unsure about

**How Swift encodes the category enums.** A category could arrive as `"table"`,
as `{"table": {}}`, or as `{"door": {"isOpen": false}}` when the case carries an
associated value. The parser accepts all three, but I do not know which one you
actually produce, or whether `Surface.Category` and `Object.Category` agree.

**Whether `simd_float4x4` really serialises as four columns.** I convert on that
assumption, and it matters: read column-major data as row-major and every
object in the shop lands at the origin. The parser will not warn you, the model
will just be wrong.

**The exact top-level key names.** I read `walls`, `doors`, `windows`,
`openings`, `floors`, `objects`. If the encoder nests these under `sections` or
a `story`, I will find nothing and raise.

## Also worth capturing

`coverage.json` is yours to define, but please key it by the same element UUIDs
RoomPlan gives the surfaces, so the rescan prompts can point at a specific wall.

And the `metadataURL` mapping from the USDZ export. USD prim names cannot be
UUIDs — hyphens are stripped and leading digits are illegal, so they collide
into `Cube_001`. I hit this building the fixture and worked around it with an
explicit map; RoomPlan's metadata file is the real version of that, and without
it nothing downstream can tie a mesh back to the object a check is about.
