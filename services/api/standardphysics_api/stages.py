"""Every stage a real capture goes through, each calling the lane that owns it.

    ingest    Lane B  parse_room_json
    label     Lane B  Astra label and clean, passed through until it ships
    assess    Lane C  assess, with the human verification ledger
    geometry  Lane B  usdz_to_glb through RoomPlan's mapping, else export_glb
    renders   Lane B  render_finding per locatable finding

Swapping an implementation means changing one field of `Stages`. Geometry and
renders need Blender and run after the scan is ready, so a slow export never
holds up the findings.
"""

from __future__ import annotations

import json
import logging
import pathlib
import threading
from collections.abc import Callable
from dataclasses import dataclass, field

from standardphysics_agents import VerificationLedger, assess, load_ledger, load_pack
from standardphysics_agents.fix import FixOutcome, propose_fix
from standardphysics_contracts import Assessment, Finding, Scenario, SceneGraph
from standardphysics_pipeline import PipelineMeasurements, blender, parse_room_json

log = logging.getLogger(__name__)

PREVIEW_REVIEWER = "unverified preview (development only)"


def pass_through(graph: SceneGraph) -> SceneGraph:
    return graph


def preview_ledger() -> VerificationLedger:
    ledger = VerificationLedger()
    for rule in load_pack().rules:
        ledger = ledger.record(rule, verified_by=PREVIEW_REVIEWER)
    return ledger


@dataclass
class Stages:
    ledger_factory: Callable[[], VerificationLedger] = load_ledger
    measure: PipelineMeasurements = field(default_factory=PipelineMeasurements)
    label: Callable[[SceneGraph], SceneGraph] = pass_through
    export_glb: Callable[[SceneGraph, pathlib.Path], pathlib.Path] = blender.export_glb
    usdz_to_glb: Callable[..., blender.ConversionResult] = blender.usdz_to_glb
    render_finding: Callable[..., pathlib.Path] = blender.render_finding
    _assess_lock: threading.Lock = field(default_factory=threading.Lock, repr=False)

    def ingest(self, room_json: pathlib.Path, scan_id) -> SceneGraph:
        graph = parse_room_json(json.loads(room_json.read_bytes()), scan_id=scan_id)
        return self.label(graph)

    def assess(self, graph: SceneGraph, scenario: Scenario, pass_number: int) -> Assessment:
        with self._assess_lock:
            result = assess(graph, scenario, self.measure, ledger=self.ledger_factory(), pass_number=pass_number)
        for missing in result.unevaluated:
            log.info("rule %s not evaluated: %s", missing.rule_id, missing.waiting_on)
        return result.assessment

    def propose(self, graph: SceneGraph, scenario: Scenario, targets: list[Finding]) -> FixOutcome:
        """Lane C's fix agent: one arrangement that clears the targets, or one thing to ask."""
        with self._assess_lock:
            return propose_fix(graph, scenario, self.measure, targets, rules=load_pack(), ledger=self.ledger_factory())

    def geometry(
        self,
        graph: SceneGraph,
        out: pathlib.Path,
        usdz: pathlib.Path | None,
        mapping: pathlib.Path | None,
    ) -> pathlib.Path | None:
        """The scanned mesh when every object keeps its identity, else boxes from the graph."""
        scanned = self._scanned_mesh(out, usdz, mapping)
        if scanned is not None:
            return scanned
        try:
            return self.export_glb(graph, out)
        except (FileNotFoundError, blender.BlenderError) as exc:
            log.warning("no display geometry for %s: %s", graph.scan_id, exc)
            return None

    def _scanned_mesh(
        self, out: pathlib.Path, usdz: pathlib.Path | None, mapping: pathlib.Path | None
    ) -> pathlib.Path | None:
        if usdz is None or mapping is None:
            return None
        try:
            converted = self.usdz_to_glb(usdz, out, mapping)
        except (FileNotFoundError, blender.BlenderError) as exc:
            log.info("usdz_to_glb failed, exporting from the graph: %s", exc)
            return None
        if not converted.fully_identified:
            log.info("usdz_to_glb left %s meshes unmapped, exporting from the graph", converted.unmapped_count)
            return None
        return converted.glb_path

    def renders(self, graph: SceneGraph, assessment: Assessment, directory: pathlib.Path, url_for) -> Assessment:
        findings = [self._rendered(graph, finding, directory, url_for) for finding in assessment.findings]
        return assessment.model_copy(update={"findings": findings})

    def _rendered(self, graph, finding, directory: pathlib.Path, url_for):
        if finding.locus is None:
            return finding
        target = directory / f"{finding.id}.png"
        try:
            if not target.exists():
                self.render_finding(graph, finding.locus, target)
        except (FileNotFoundError, blender.BlenderError) as exc:
            log.warning("no render for finding %s: %s", finding.id, exc)
            return finding
        locus = finding.locus.model_copy(update={"render_url": url_for(finding.id)})
        return finding.model_copy(update={"locus": locus})
