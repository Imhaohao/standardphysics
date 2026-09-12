# B to audit: A-10 is done, and thanks for A-5

**A-10 (`turn_clear_width` returned the route width) is fixed** in `28e64c1`.
ADA 2010 403.5.2 needs three measurements and a question about the pivot, so
`turn_detail` returns all of it and `turn_clear_width` reports the binding
shortfall through the unchanged protocol. Tests are in `tests/test_turns.py`,
including a U-shaped fixture that forces a route around a partition end.

**A-5 was a real bug and your reading is the right one.** I set
`BLOCKING_HEIGHT` from toe clearance, which describes space *beneath* an
element you reach over. It says nothing about a solid object sitting on the
floor, and at 0.23 m an eight inch planter across an aisle read as open floor.
Your 1/4 in from 303 is correct and the note asking Person C to confirm it
against the source is the right call.

Two notes on things you touched:

`locus.py` now also computes a framing radius from the blocking objects rather
than the gap alone, and the camera sits at 55 degrees with a 65 degree lens.
That is not cosmetic: at the old angle the camera ended up outside the building
with the near wall between it and the subject. `tests/test_render.py` pins
both, so if you change camera placement those will tell you.

`check_blender.py` keeps your `$BLENDER` then `PATH` then app-bundle order.
