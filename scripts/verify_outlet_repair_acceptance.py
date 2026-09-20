"""Executable acceptance harness and completion verifier for the outlet feature repair.

Validates receipts in PROGRESS_MOFFETT_OUTLET_REPAIR.json against docs/outlet-repair-acceptance.json.
Checks:
- All required cases present and passed with required receipt fields.
- No synthetic artifacts claimed as real_capture.
- All 8 targeted mutations killed by behavioral assertions.
- Current gate pass statuses and overall terminal status.
"""

from __future__ import annotations

import json
import pathlib
import sys
from typing import Any


def verify_acceptance(root_dir: pathlib.Path) -> dict[str, Any]:
    contract_path = root_dir / "docs/outlet-repair-acceptance.json"
    progress_path = root_dir / "PROGRESS_MOFFETT_OUTLET_REPAIR.json"

    if not contract_path.is_file():
        return {"ok": False, "error": f"Contract file not found: {contract_path}"}
    if not progress_path.is_file():
        return {"ok": False, "error": f"Progress file not found: {progress_path}"}

    with open(contract_path) as f:
        contract = json.load(f)
    with open(progress_path) as f:
        progress = json.load(f)

    required_gate_ids = contract["required_gate_ids"]
    required_receipt_fields = contract["required_receipt_fields"]
    cases = contract["cases"]
    mutations = contract["mutations"]

    receipts = progress.get("receipts", {})
    mutation_receipts = progress.get("mutation_receipts", {})

    errors: list[str] = []
    case_status: dict[str, str] = {}

    # 1. Validate each case
    for case in cases:
        case_id = case["id"]
        gate_id = case["gate"]
        kind = case["kind"]

        if case_id not in receipts:
            case_status[case_id] = "missing"
            errors.append(f"Case {case_id} (Gate {gate_id}) has no receipt in PROGRESS_MOFFETT_OUTLET_REPAIR.json")
            continue

        receipt = receipts[case_id]

        # Check required fields
        for field in required_receipt_fields:
            if field not in receipt:
                errors.append(f"Case {case_id} receipt is missing required field: {field}")

        # Check exit status / assertion status
        status = receipt.get("exit_status_or_assertion_status")
        if status not in (0, "passed", "PASS", "ok", True):
            errors.append(f"Case {case_id} failed with status: {status}")
            case_status[case_id] = "failed"
            continue

        # Check synthetic vs real_capture constraint
        if kind == "real_capture":
            if receipt.get("evidence_kind") != "real_capture":
                errors.append(f"Case {case_id} requires real_capture evidence, but got {receipt.get('evidence_kind')}")
                case_status[case_id] = "invalid_evidence"
                continue

        case_status[case_id] = "passed"

    # 2. Validate mutations
    mutation_status: dict[str, str] = {}
    for m in mutations:
        m_id = m["id"]
        if m_id not in mutation_receipts:
            mutation_status[m_id] = "missing"
            errors.append(f"Mutation {m_id} has no receipt")
            continue
        m_rec = mutation_receipts[m_id]
        if not m_rec.get("assertion_failed", False):
            errors.append(f"Mutation {m_id} survived! (did not trigger expected behavioral failure)")
            mutation_status[m_id] = "survived"
            continue
        mutation_status[m_id] = "killed"

    # 3. Evaluate gates
    passed_gates: list[str] = []
    gate_results: dict[str, str] = {}
    for gate_id in required_gate_ids:
        gate_cases = [c for c in cases if c["gate"] == gate_id]
        all_passed = all(case_status.get(c["id"]) == "passed" for c in gate_cases)
        if gate_id == "G8":
            all_mutations_killed = all(mutation_status.get(m["id"]) == "killed" for m in mutations)
            all_passed = all_passed and all_mutations_killed

        if all_passed and gate_cases:
            passed_gates.append(gate_id)
            gate_results[gate_id] = "passed"
        else:
            gate_results[gate_id] = "open"

    total_gates = len(required_gate_ids)
    progress_pct = 100.0 * len(passed_gates) / total_gates

    # Determine terminal status
    if len(passed_gates) == total_gates:
        terminal_status = "verified_web_feature"
    elif all(gate_results.get(g) == "passed" for g in ["G0", "G1", "G2", "G3", "G4", "G5", "G6", "G7", "G8", "G10"]) and gate_results.get("G9") != "passed":
        terminal_status = "implementation_ready_real_acceptance_blocked"
    else:
        terminal_status = "incomplete"

    return {
        "ok": len(errors) == 0,
        "errors": errors,
        "progress_pct": progress_pct,
        "passed_gates": passed_gates,
        "gate_results": gate_results,
        "terminal_status": terminal_status,
        "case_status": case_status,
        "mutation_status": mutation_status,
    }


def main():
    root_dir = pathlib.Path(__file__).resolve().parents[1]
    result = verify_acceptance(root_dir)
    print(json.dumps(result, indent=2))
    if not result["ok"]:
        print(f"\nVerification incomplete: {len(result['errors'])} errors, progress: {result['progress_pct']:.1f}%")
        sys.exit(1)
    else:
        print(f"\nAll required gates passed! Terminal status: {result['terminal_status']}")
        sys.exit(0)


if __name__ == "__main__":
    main()
