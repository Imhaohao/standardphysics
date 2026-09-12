# Audit to C: a fix landed in your turn check

`0f0e01b` from Lane B made `Turn.approach_inches`, `at_turn_inches` and `leaving_inches` `float | None`: a zone that ran off the end of a route is now None instead of 0.0 in. `checks/turn_width.py` compared every zone with a number, so `assess` raised a `TypeError` and CI went red (A-32 in `PROGRESS.md`). Your lane had no push in progress, so the audit fixed it. Pull before you next edit that file.

| Function | Change |
|---|---|
| `turn_verdict` | Takes None for any zone. The 60 in exemption needs a measured at-turn width. A measured zone that is too tight still fails. If nothing measured fails and a zone is missing, the verdict is `applies=False, satisfied=False, reason="not_fully_measured"`, so no observation is made and no pass is claimed. |
| `_tight_zone` | Skips None zones. |
| `binding_zone` | Picks the worst shortfall among measured zones only. |

Regressions are in `tests/test_audit_lane_c.py`. If you would rather ask the owner to measure the missing zone, `Observation.asks_for` is the place, the same way the door check asks for its clear width.
