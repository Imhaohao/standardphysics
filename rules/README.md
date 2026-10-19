# rules

The rulepack as data. Every threshold, citation and source link the product reports lives here; `sp-core` evaluates it and never hard-codes a number.

| File | What it holds |
|---|---|
| `metrics.json` | Object categories (RoomPlan's 16 classes plus detector classes, each with a `canonical` id), element kinds, and every metric a rule may read: id, unit, value type, which categories it is defined for, how it is derived, and whether it comes from scan geometry (`measured`), a `photo`, or an `owner` answer. `sp-core` needs an extractor or observation key for each one. |
| `ada2010.json` | 2010 ADA Standards for Accessible Design rules, plus the 28 CFR part 36 provisions that shape findings (36.211 maintenance, 36.304 barrier removal). |
| `cbc11b.json` | 2025 California Building Code Chapter 11B rules (effective 2026-01-01), with California-only rules and `stricter_than` links to the ADA rules they tighten. |
| `coverage.json` | Every section considered, per jurisdiction: `covered` (with rule ids), `not_applicable_to_scope`, or `deferred`, each with a reason. |
| `precedents.json` | Cases, DOJ guidance and statutes that inform rules, each with what was verified and when. |
| `schema/` | JSON Schemas for the rule files and the metric catalog, including the scoping-condition and test semantics. |
| `tools/validate.py` | Stdlib validator; run `python3 -I rules/tools/validate.py`. |

## How a rule evaluates

A rule applies to each subject whose canonical category is in `applies_to`. `scoping.when` filters subjects. A condition metric that isn't defined for the subject's category counts as false. A defined metric with no value follows `scoping.when_unknown`. The `test` then runs, and any missing value makes the finding `needs_info`, never `pass`. When a measurement sits within `tolerance` of a limit, the finding is also `needs_info`, because LiDAR error is about the size of the margin and a person should confirm it. ADA and CBC findings are reported separately. Where a CBC rule lists an ADA rule in `stricter_than`, the CBC result governs in California.

## Adding a rule

1. Read the requirement in the primary text (access-board.gov for the ADA Standards, the ICC/BSC edition for the CBC) and put that link in `source_url`.
2. Reuse a metric from `metrics.json`. If none fits, add one with a derivation precise enough that the core team can implement it, and tell them.
3. Add the rule to the jurisdiction file. The id is `ADA-<section>-<slug>` or `CBC-11B-<section>-<slug>`. Set `evidence` to how the value is actually obtained, set `counterpart`, and add `stricter_than` when the CBC rule is stricter. Leave `verified_by` and `verified_at` null.
4. Add or update the section's entry in `coverage.json`.
5. Run the validator. It checks the schemas, unique ids, metrics and units, that every test metric is defined for every subject, that the evidence label is honest, the cross-jurisdiction links, coverage completeness and precedent references.

## Review status

Nothing here has had legal review. Every rule's `verified_by` is null until a CASp or an attorney signs it off, and the product must not present findings as legal conclusions before that. The ADA values were read from the U.S. Access Board's online 2010 Standards. The CBC values were read from a third-party transcription of the 2025 CBC (`source_kind: transcription`; the official text is at `official_url`) and need checking against the official edition. Rule and precedent `notes` record the specific points that still need confirming.
