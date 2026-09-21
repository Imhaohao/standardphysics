"""Policy-enforcing evaluation CLI for benchmark version 3.

One entry point reads the supplied policy JSON, loads the baseline and
candidate run records, derives the gates and writes the result.  It exits
nonzero on invalid evidence, schema problems, unexpected files, missing views
or violated prerequisites; a measured quality rejection is a success (exit 0)
with ``completed_rejected`` and a null selection score, per the policy's
execution contract.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from standardphysics_pipeline.render_efficiency.metrics import MetricError
from standardphysics_pipeline.render_efficiency.policy import (
    PolicyError,
    evaluate,
    load_policy,
)


def _expected_validation_rois(rois_path: Path | None) -> set[str]:
    if rois_path is None or not rois_path.is_file():
        return set()
    raw = json.loads(rois_path.read_text())
    validation = raw.get("validation") or {}
    return {str(roi_id) for roi_id in validation.keys()}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--policy", type=Path, required=True,
                        help="JSON policy the evaluator enforces (it does not restate thresholds)")
    parser.add_argument("--baseline", type=Path, required=True, help="baseline run record JSON")
    parser.add_argument("--candidate", type=Path, required=True, help="candidate run record JSON")
    parser.add_argument("--rois", type=Path, default=None,
                        help="preregistered ROI JSON; its validation section supplies expected ROI IDs")
    parser.add_argument("--out", type=Path, required=True, help="result JSON destination")
    args = parser.parse_args()

    if args.out.exists():
        print(f"refusing to overwrite existing result destination: {args.out}", file=sys.stderr)
        return 2

    try:
        policy = load_policy(args.policy)
    except (PolicyError, OSError, ValueError) as error:
        print(f"policy invalid: {error}", file=sys.stderr)
        return 2

    try:
        baseline = json.loads(args.baseline.read_text())
        candidate = json.loads(args.candidate.read_text())
    except (OSError, ValueError) as error:
        print(f"run records unreadable: {error}", file=sys.stderr)
        return 2

    try:
        expected_rois = _expected_validation_rois(args.rois)
        result = evaluate(policy, baseline, candidate, expected_rois)
    except (PolicyError, MetricError, ZeroDivisionError, KeyError) as error:
        result = {
            "status": "blocked_missing_evidence",
            "selection_score": None,
            "score_reason": f"evaluation refused: {error}",
            "gate_results": {},
        }
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n")
        print(json.dumps(result, indent=2), file=sys.stderr)
        return 1

    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n")
    summary = {k: result.get(k) for k in ("status", "selection_score", "selection_lane", "score_reason")}
    print(json.dumps(summary, indent=2))
    if result.get("status") == "selected_for_review":
        return 0
    if result.get("status") == "completed_rejected":
        return 0
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
