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
from pathlib import Path
from typing import Callable

from .assess import assess
from .evaluation import evaluate, save
from .evaluation.scorers import LOWER_IS_BETTER
from .loop import run_loop
from .router import LocalPolicyRouter, TypeSafeRouter
from .rules import RuleSpec, load_ledger, load_pack, save_ledger
from .tracing import init as init_tracing
from .tracing import is_live

READ_BACK_TOLERANCE = 1e-9

PROVIDERS = ("stub", "pipeline")

ROUTERS = ("typesafe", "local")

DEFAULT_EVALUATION_PATH = "runs/evaluation.json"


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
    _print_rule(load_pack().by_id(args.rule_id), load_ledger())
    return 0


def _print_rule(rule: RuleSpec, ledger) -> None:
    print(f"{rule.id}\n")
    print(f"  {rule.title}")
    print(f"  {rule.citation.authority} {rule.citation.display()}")
    print(f"  {rule.citation.url or ''}")
    print(f"  threshold: {rule.threshold:g} {rule.unit} ({rule.comparison})")
    for name, value in sorted(rule.parameters.items()):
        print(f"  {name}: {value:g}")
    print(f"  evidence: {rule.evidence}")
    print(f"  state: {_state(rule, ledger)}\n")
    print(f"  {rule.source_text}\n")
    if rule.review_note:
        print(f"  review note: {rule.review_note}\n")


def _read_back(rule: RuleSpec, given: float | None) -> bool:
    if given is not None:
        return math.isclose(given, rule.threshold, abs_tol=READ_BACK_TOLERANCE)
    typed = input(f"Type the number you read in {rule.citation.section}: ").strip()
    return _matches(typed, rule)


def _verify(args) -> int:
    pack, ledger = load_pack(), load_ledger()
    rule = pack.by_id(args.rule_id)
    _print_rule(rule, ledger)
    if not _read_back(rule, args.threshold):
        print(
            f"That is not the threshold in the pack. {rule.id} stays off.",
            file=sys.stderr,
        )
        return 1
    save_ledger(ledger.record(rule, verified_by=args.by, note=args.note))
    print(f"{rule.id} is on. {rule.threshold:g} {rule.unit}, read by {args.by}.")
    return 0


def _review(args) -> int:
    """Walk every rule nobody has read yet, one section at a time."""
    pack = load_pack()
    waiting = [r for r in pack.within_tier(args.tier) if not load_ledger().verifies(r)]
    if not waiting:
        print(f"Every tier {args.tier} rule has a reader.")
        return 0

    print(f"{len(waiting)} rules to read. Enter a blank line to stop.\n")
    for rule in waiting:
        if _review_one(rule, args.by) is False:
            break
    return 0


def _review_one(rule: RuleSpec, reviewer: str) -> bool:
    _print_rule(rule, load_ledger())
    typed = input(
        f"Number you read in {rule.citation.section} (blank to stop): "
    ).strip()
    if not typed:
        return False
    if not _matches(typed, rule):
        print(f"  That is not what the pack says. {rule.id} stays off.\n")
        return True
    save_ledger(load_ledger().record(rule, verified_by=reviewer))
    print(f"  {rule.id} is on.\n")
    return True


def _matches(typed: str, rule: RuleSpec) -> bool:
    try:
        return math.isclose(float(typed), rule.threshold, abs_tol=READ_BACK_TOLERANCE)
    except ValueError:
        return False


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


def _count(number: int, noun: str) -> str:
    return f"{number} {noun}" if number == 1 else f"{number} {noun}s"


def _router(name: str):
    """TypeSafe when it is configured, and a labelled local policy when not."""
    if name == "local":
        return LocalPolicyRouter()
    router = TypeSafeRouter()
    if router.configured:
        return router
    print(
        "TYPESAFE_API_KEY and TYPESAFE_BASE_URL are not set. "
        "Running the local policy, labelled as one.",
        file=sys.stderr,
    )
    return LocalPolicyRouter()


NOTHING_ENABLED = (
    'No checks are enabled. Run: rules review --by "<name>"'
)


def _nothing_enabled(pack, ledger) -> bool:
    if pack.enabled(ledger, max_tier=1):
        return False
    print(NOTHING_ENABLED, file=sys.stderr)
    return True


def _evaluate(args) -> int:
    pack, ledger = load_pack(), load_ledger()
    if _nothing_enabled(pack, ledger):
        return 1
    result = evaluate(
        measure=_measurements(args.provider),
        rules=pack,
        ledger=ledger,
        run_fixes=not args.no_fixes,
    )
    print(f"rule pack {result.rulepack_version}, {len(result.outcomes)} cases")
    print(f"completed: {result.completed}")
    for name, value in sorted(result.scores.items()):
        direction = "lower is better" if name in LOWER_IS_BETTER else ""
        print(f"  {name:24} {value:.4f}  {direction}")
    for case_id in result.failures:
        print(f"  failed: {case_id}", file=sys.stderr)
    written = save(result, Path(args.out))
    print(f"per-case results: {written}")
    if result.weave_url:
        print(f"traces: {result.weave_url}")
    return 0 if result.completed else 1


def _loop(args) -> int:
    pack, ledger = load_pack(), load_ledger()
    if _nothing_enabled(pack, ledger):
        return 1
    graph, scenario = _fixture_shop()
    steps = run_loop(
        graph,
        scenario,
        _measurements(args.provider),
        _router(args.router),
        rules=pack,
        ledger=ledger,
    )
    for step in steps:
        action = step.action or f"nothing authorized ({step.rejected})"
        print(f"pass {step.pass_number}: {action}")
        print(f"  {_count(len(step.assessment.problems), 'problem')}, "
              f"{_count(len(step.assessment.questions), 'question')}")
        if step.message:
            print(f"  {step.message}")
        gate = step.result.gate
        if gate:
            print(f"  gate: {'accepted' if gate.accepted else 'rejected'}, "
                  f"{gate.shortfall_before:.1f} in short -> {gate.shortfall_after:.1f}")
    return 0


HANDLERS: dict[str, Callable[[argparse.Namespace], int]] = {
    "rules.list": _list,
    "rules.show": _show,
    "rules.verify": _verify,
    "rules.review": _review,
    "rules.second-check": _second_check,
    "check": _check,
    "evaluate": _evaluate,
    "loop": _loop,
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

    review = sub.add_parser("review", help="read every unverified rule in turn")
    review.add_argument("--by", required=True)
    review.add_argument("--tier", type=int, default=1)

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

    evaluation = commands.add_parser(
        "evaluate", help="score the checks against the labelled dataset"
    )
    evaluation.add_argument("--provider", choices=PROVIDERS, default="pipeline")
    evaluation.add_argument("--out", default=DEFAULT_EVALUATION_PATH)
    evaluation.add_argument(
        "--no-fixes", action="store_true", help="skip the rearrangement cases"
    )

    loop = commands.add_parser("loop", help="run the whole loop on the fixture shop")
    loop.add_argument("--provider", choices=PROVIDERS, default="pipeline")
    loop.add_argument("--router", choices=ROUTERS, default="typesafe")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    init_tracing()
    key = (
        f"{args.command}.{args.rules_command}"
        if args.command == "rules"
        else args.command
    )
    return HANDLERS[key](args)


if __name__ == "__main__":
    raise SystemExit(main())
