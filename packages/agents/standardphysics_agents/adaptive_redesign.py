"""Bounded Astra proposals with deterministic validation and Jev ranking."""

from __future__ import annotations

import math
from dataclasses import dataclass

from standardphysics_contracts import AdaptiveRoundResult, SceneGraph, graph_hash

from .accessibility_intelligence import AccessibilityIntelligence, LayoutCandidate
from .mesh_collision import MeshCollisionIndex
from .redesign import propose_redesign
from .router import SystemOneClient, SystemOneError, TypeSafeCallBudget
from .workflows import FunctionalProfile, Workflow, evaluate_workflow


@dataclass(frozen=True)
class AdaptiveRedesignResult:
    """The best recommendation; the measured graph is never modified."""

    graph: SceneGraph | None
    rounds: tuple[AdaptiveRoundResult, ...]
    astra_calls: int


def run_adaptive_redesign(
    measured_graph: SceneGraph,
    *,
    workflows: list[Workflow],
    profiles: list[FunctionalProfile],
    measure,
    rules,
    ledger,
    rounds: int,
    budget: TypeSafeCallBudget,
    collision_index: MeshCollisionIndex | None = None,
    starting_graph: SceneGraph | None = None,
    astra_client=None,
    intelligence: AccessibilityIntelligence | None = None,
) -> AdaptiveRedesignResult:
    """Try one candidate per round and stop at the first unsafe or unhelpful step."""
    if not 1 <= rounds <= 8:
        raise ValueError("adaptive redesign rounds must be between 1 and 8")
    if not workflows or not profiles:
        raise ValueError("adaptive redesign needs workflows and profiles")

    original_hash = graph_hash(measured_graph)
    current = starting_graph or measured_graph
    accepted_any = False
    history: list[AdaptiveRoundResult] = []
    jev = intelligence or AccessibilityIntelligence(SystemOneClient(budget=budget))

    for round_number in range(1, rounds + 1):
        base_hash = graph_hash(current)
        current_evidence = _layout_evidence(
            measured_graph, current, workflows, profiles, measure, collision_index
        )
        proposal = propose_redesign(
            current,
            workflows,
            profiles,
            [current_evidence],
            measure,
            rules=rules,
            ledger=ledger,
            collision_index=collision_index,
            model=astra_client,
        )
        if not proposal.accepted or proposal.graph is None:
            history.append(
                AdaptiveRoundResult(
                    round=round_number,
                    base_graph_hash=base_hash,
                    astra_model=proposal.model,
                    accepted=False,
                    reasons=list(proposal.reasons),
                )
            )
            break

        candidate = proposal.graph
        candidate_evidence = _layout_evidence(
            measured_graph, candidate, workflows, profiles, measure, collision_index
        )
        current_id = f"current:{base_hash}"
        candidate_id = f"candidate:{graph_hash(candidate)}"
        try:
            ranking = jev.rank_layouts(
                [
                    LayoutCandidate(
                        id=current_id,
                        deterministic_checks_passed=True,
                        usability_evidence=current_evidence,
                        disruption_evidence=current_evidence["disruption"],
                    ),
                    LayoutCandidate(
                        id=candidate_id,
                        deterministic_checks_passed=True,
                        usability_evidence=candidate_evidence,
                        disruption_evidence=candidate_evidence["disruption"],
                    ),
                ]
            )
        except SystemOneError as error:
            history.append(
                AdaptiveRoundResult(
                    round=round_number,
                    base_graph_hash=base_hash,
                    astra_model=proposal.model,
                    accepted=False,
                    reasons=[str(error)],
                )
            )
            break

        preferred = ranking[0].candidate.id
        accepted = preferred == candidate_id
        history.append(
            AdaptiveRoundResult(
                round=round_number,
                base_graph_hash=base_hash,
                astra_model=proposal.model,
                accepted=accepted,
                reasons=(
                    ["deterministic_improvement_and_jev_preference"]
                    if accepted
                    else ["jev_preferred_current_layout"]
                ),
                jev_preferred_candidate=preferred,
            )
        )
        if not accepted:
            break
        current = candidate
        accepted_any = True

    if graph_hash(measured_graph) != original_hash:
        raise AssertionError("adaptive redesign changed the measured scan")
    return AdaptiveRedesignResult(
        graph=current if accepted_any else None,
        rounds=tuple(history),
        astra_calls=len(history),
    )


def _layout_evidence(
    measured: SceneGraph,
    layout: SceneGraph,
    workflows: list[Workflow],
    profiles: list[FunctionalProfile],
    measure,
    collision_index: MeshCollisionIndex | None,
) -> dict:
    evaluations = [
        evaluate_workflow(
            layout,
            workflow,
            profile,
            measure,
            collision_index=collision_index,
        )
        for workflow in workflows
        for profile in profiles
    ]
    legs = [leg for evaluation in evaluations for leg in evaluation.legs]
    interactions = [
        interaction
        for evaluation in evaluations
        for interaction in evaluation.interactions
    ]
    original = {node.id: node for node in measured.nodes}
    moved = [
        node
        for node in layout.nodes
        if node.id in original and node.transform != original[node.id].transform
    ]
    translation = sum(
        math.dist(
            (node.transform.position.x, node.transform.position.y),
            (
                original[node.id].transform.position.x,
                original[node.id].transform.position.y,
            ),
        )
        for node in moved
    )
    return {
        "graph_hash": graph_hash(layout),
        "workflow_profile_evaluations": len(evaluations),
        "passed_evaluations": sum(item.passed for item in evaluations),
        "route_legs": len(legs),
        "passed_route_legs": sum(leg.passed for leg in legs),
        "reachable_interactions": sum(item.reachable is True for item in interactions),
        "unreachable_interactions": sum(item.reachable is False for item in interactions),
        "interactions_needing_measurement": sum(
            item.needs_measurement for item in interactions
        ),
        "disruption": {
            "moved_object_count": len(moved),
            "total_translation_meters": translation,
            "fixed_objects_moved": sum(not node.movable for node in moved),
            "inventory_preserved": {node.id for node in measured.nodes}
            == {node.id for node in layout.nodes},
        },
    }


__all__ = ["AdaptiveRedesignResult", "run_adaptive_redesign"]
