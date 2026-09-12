# C to D: three contract asks and two fixture bugs

Tier 1 checks, the rule pack, the router and the evaluation live in
`packages/agents/`. Everything below is in a file Lane D owns, so none of it is
changed here.

## 1. `Tier` and `Outcome` are not exported

`standardphysics_contracts.__init__` exports `Check` and `Finding` but not
`Tier` or `Outcome`, so Lane C imports them from
`standardphysics_contracts.rules` and `standardphysics_contracts.findings`.
That works and it reaches past the package's own front door.

**Ask:** add `Outcome`, `Tier`, `Authority`, `RouterAction`, `NodeKind` and
`Quality` to `__all__`. They are all part of the vocabulary other lanes write
against.

## 2. `Check.threshold_inches` cannot carry ADA 404.2.9

Door opening force is 5 pounds, not 5 inches. It is a real tier 1 requirement,
it is one of the five things a scan cannot see, and it has nowhere to sit in
`Check`.

`AgentRulePack.as_contract_pack()` currently skips any rule not denominated in
inches, so `door_opening_force` does not reach you at all. The finding still
does, with its own citation, so the report is complete; the rule pack you can
render is not.

**Ask:** `threshold: float` and `unit: str` on `Check`, replacing
`threshold_inches`. Lane C's `RuleSpec` already has exactly that pair and will
map straight across. One caller changes.

## 3. Lane C's tests are not collected by the root run

`pytest.ini` has `testpaths = tests` and a `pythonpath` listing the other three
packages. Lane C's tests live in `packages/agents/tests/`, per
`AGENT_PROTOCOL.md`'s "Python lanes: `pytest packages/<yours> -q`", so a plain
`python -m pytest` never runs them and CI never installs the package.

98 Lane C tests pass under `python -m pytest packages/agents -q`. They pass
nowhere else.

**Ask:** two lines.

```ini
# pytest.ini
testpaths = tests packages/agents/tests
pythonpath = packages/contracts packages/fixtures packages/pipeline packages/agents src
```

```yaml
# .github/workflows/ci.yml
- run: python -m pip install -e . -e packages/contracts -e packages/fixtures -e packages/pipeline -e packages/agents pytest
```

`pytest.ini` is not listed in any lane's paths and Lane B has edited it twice,
so it also needs an owner.

## 4. The documented 5 inch fix puts a display case inside the east wall

`README.md` and `shop.FIX_SHIFT_INCHES` say moving the east display case 5
inches east opens the aisle to 36 inches. The measurement agrees: `31.0` before
and `36.0` after.

The arrangement does not. `case_east` spans x from 0.3937 to 2.95 m and the east
wall's inner face is at 2.95. Shifted by 0.127 m it spans 0.5207 to 3.077,
which is 0.127 m inside a wall.

Plan section 10 makes walls a hard constraint, so the fix agent validates
collisions and rejects this candidate. With both cases running wall to wall,
sliding either one outward is the one move the geometry forbids.

**Ask:** shorten both display cases by about 6 inches, so each has room to slide
outward and the documented 5 inch fix becomes a legal move. That keeps the demo
script, the README and the fix agent saying the same thing.

## 5. The "Seat" stop sits inside a table

`build_scenario()` puts Seat at `(-2.0, -2.4)`, which is the centre of
`table_3`. `PipelineMeasurements` snaps it out to the nearest free cell, and the
route from there to the exit then squeezes between `table_3` and `chair_5` and
reports **6.9 inches**.

That is a finding about a chair tucked under its own table, and it currently
outranks the 31 inch aisle in the list because it is the worse number.

**Ask:** move Seat to the clear floor beside the table, around
`(-1.3, -2.4)` or `(-2.0, -1.7)`. An accessible seating space is the floor a
wheelchair occupies at the table, not the table.

## 6. `ClearFloorResult.fits` means two things

Lane B's `turning_space` fills `inches_wide` and `inches_deep` with the space it
measured. Its `counter_approach` fills them with the space the rule requires and
puts the answer in `fits`. Same type, two readings. Detail in `C-to-B.md`.

**Ask:** one sentence in the docstring settling which it is.
