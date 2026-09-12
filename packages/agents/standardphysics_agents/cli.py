"""The command line a person uses to enable a check.

Verification is the one thing in this lane an agent must not do alone, so it
gets a real interface rather than a JSON file to hand-edit. `verify` prints the
sentence from the standard and then asks for the number back. Typing it is the
confirmation: it cannot be satisfied by someone who did not read the section.
"""

from __future__ import annotations

import argparse
import math
import sys
from typing import Callable

from .assess import assess
from .rules import RuleSpec, load_ledger, load_pack, save_ledger

READ_BACK_TOLERANCE = 1e-9

PROVIDERS = ("stub", "pipeline")


def _measurements(name: str):
    if name == "pipeline":
        from standardphysics_pipeline import PipelineMeasurements

        return PipelineMeasurements()
    from standardphysics_fixtures import FixtureMeasurements

    return FixtureMeasurements()


def _fixture_shop():
    from standardphysics_fixtures import build_graph, build_scenario

    return build_graph(), build_scenario()


def _state(rule: RuleSpec, ledger) -> str:
    entry = ledger.entry_for(rule)
    if entry is None:
        return "waiting on a person"
    if entry.second_check_by:
        return f"verified by {entry.verified_by}, checked by {entry.second_check_by}"
    return f"verified by {entry.verified_by}, wants a second reader"


def _list(args) -> int:
    pack, ledger = load_pack(), load_ledger()
    for rule in pack.within_tier(args.tier):
        print(
            f"{rule.id:28} tier {rule.tier}  "
            f"{rule.threshold:>6g} {rule.unit:<4} {rule.comparison:<9} "
            f"{rule.citation.display():<48} {_state(rule, ledger)}"
        )
    return 0


def _show(args) -> int:
    rule = load_pack().by_id(args.rule_id)
    print(f"{rule.id}\n")
    print(f"  {rule.title}")
    print(f"  {rule.citation.authority} {rule.citation.display()}")
    print(f"  {rule.citation.url or ''}")
    print(f"  threshold: {rule.threshold:g} {rule.unit} ({rule.comparison})")
    for name, value in sorted(rule.parameters.items()):
        print(f"  {name}: {value:g}")
    print(f"  evidence: {rule.evidence}")
    print(f"  state: {_state(rule, load_ledger())}\n")
    print(f"  {rule.source_text}\n")
    if rule.review_note:
        print(f"  review note: {rule.review_note}\n")
    return 0


def _read_back(rule: RuleSpec, given: float | None) -> bool:
    if given is not None:
        return math.isclose(given, rule.threshold, abs_tol=READ_BACK_TOLERANCE)
    typed = input(f"Type the number you read in {rule.citation.section}: ").strip()
    try:
        return math.isclose(float(typed), rule.threshold, abs_tol=READ_BACK_TOLERANCE)
    except ValueError:
        return False


def _verify(args) -> int:
    pack, ledger = load_pack(), load_ledger()
    rule = pack.by_id(args.rule_id)
    _show(args)
    if not _read_back(rule, args.threshold):
        print(
            f"That is not the threshold in the pack. {rule.id} stays off.",
            file=sys.stderr,
        )
        return 1
    save_ledger(ledger.record(rule, verified_by=args.by, note=args.note))
    print(f"{rule.id} is on. {rule.threshold:g} {rule.unit}, read by {args.by}.")
    return 0


def _second_check(args) -> int:
    pack, ledger = load_pack(), load_ledger()
    rule = pack.by_id(args.rule_id)
    save_ledger(ledger.second_check(rule, checked_by=args.by))
    print(f"{rule.id} has two readers.")
    return 0


def _check(args) -> int:
    graph, scenario = _fixture_shop()
    result = assess(graph, scenario, _measurements(args.provider), max_tier=args.tier)
    if not result.findings:
        print("No checks are enabled. Run: rules verify <id> --by \"<name>\"")
    for finding in result.findings:
        mark = {"problem": "!", "question": "?", "passes": " "}[finding.outcome]
        print(f"{mark} {finding.title}")
        print(f"  {finding.detail}")
        if finding.fix:
            print(f"  {finding.fix}")
        print(f"  {finding.citation.authority} {finding.citation.display()}")
    for gap in result.unevaluated:
        print(f"- {gap.rule_id} is held, waiting on {gap.waiting_on}")
    return 0


HANDLERS: dict[str, Callable[[argparse.Namespace], int]] = {
    "rules.list": _list,
    "rules.show": _show,
    "rules.verify": _verify,
    "rules.second-check": _second_check,
    "check": _check,
}


def _add_rule_commands(parent) -> None:
    rules = parent.add_parser("rules", help="the thresholds and who has read them")
    sub = rules.add_subparsers(dest="rules_command", required=True)

    listing = sub.add_parser("list", help="every rule and its state")
    listing.add_argument("--tier", type=int, default=3)

    show = sub.add_parser("show", help="one rule, with the sentence behind it")
    show.add_argument("rule_id")

    verify = sub.add_parser("verify", help="turn a check on after reading its section")
    verify.add_argument("rule_id")
    verify.add_argument("--by", required=True, help="your name, for the report")
    verify.add_argument("--note", default=None)
    verify.add_argument(
        "--threshold",
        type=float,
        default=None,
        help="the number you read, instead of being asked for it",
    )

    second = sub.add_parser("second-check", help="record a second reader")
    second.add_argument("rule_id")
    second.add_argument("--by", required=True)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="standardphysics-agents")
    commands = parser.add_subparsers(dest="command", required=True)
    _add_rule_commands(commands)

    check = commands.add_parser("check", help="run the checks on the fixture shop")
    check.add_argument("--provider", choices=PROVIDERS, default="pipeline")
    check.add_argument("--tier", type=int, default=1)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    key = (
        f"{args.command}.{args.rules_command}"
        if args.command == "rules"
        else args.command
    )
    return HANDLERS[key](args)


if __name__ == "__main__":
    raise SystemExit(main())
