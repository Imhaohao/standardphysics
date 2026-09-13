"use client";

import { useRouter } from "next/navigation";
import Link from "next/link";
import { useEffect, useMemo, useState } from "react";
import { Button } from "@/components/ui/Button";
import { getSimulation, rebuildRoom, SimulationRequestError, startSimulation } from "@/lib/simulation-client";
import { candidateMoves } from "@/lib/moves";
import type { NodeMove, SceneGraph, SimulationFeedback, SimulationStatus } from "@/types/contracts";

const SAMPLES = 1_000;
const POLL_MS = 2_000;

function isActive(status: SimulationStatus | null) {
  return status?.state === "queued" || status?.state === "running";
}

function failureSummary(feedback: SimulationFeedback) {
  return [
    `${feedback.clearance_failure_trials} clearance`,
    `${feedback.floor_plan_collision_trials} floor-plan collision`,
    `${feedback.mesh_collision_trials} mesh collision`,
    `${feedback.unreachable_interaction_trials} unreachable`,
    `${feedback.needs_measurement_trials} needs measurement`,
  ].filter((item) => !item.startsWith("0 ")).join(", ");
}

function Feedback({ feedback, labels }: { feedback: SimulationFeedback; labels: Map<string, string> }) {
  const blockers = feedback.blocking_node_ids.map((id) => labels.get(id) ?? id);
  return (
    <li className="space-y-1 rounded-lg bg-rule/30 p-3 text-sm">
      <p className="font-medium">{feedback.workflow_title}: {feedback.profile_title}</p>
      <p className="text-ink-muted">{feedback.passed_trials} passed out of {feedback.trials}; {failureSummary(feedback) || "no recorded failures"}.</p>
      {blockers.length > 0 && <p className="text-ink-muted">Blockers: {blockers.join(", ")}</p>}
    </li>
  );
}

function message(reason: unknown, fallback: string) {
  return reason instanceof Error ? reason.message : fallback;
}

function SimulationControls({ routerName, refineWithAstra, rebuilding, active, onRouter, onRefine, onRebuild, onRun }: {
  routerName: "local" | "typesafe"; refineWithAstra: boolean; rebuilding: boolean; active: boolean;
  onRouter: (router: "local" | "typesafe") => void; onRefine: (value: boolean) => void; onRebuild: () => void; onRun: () => void;
}) {
  return <div className="flex flex-wrap items-center gap-2">
    <Button variant="quiet" onClick={onRebuild} disabled={rebuilding || active}>{rebuilding ? "Rebuilding room" : "Rebuild room"}</Button>
    <label className="text-sm text-ink-muted" htmlFor="simulation-router">Route screening</label>
    <select id="simulation-router" className="rounded-lg border border-rule bg-sheet px-2 py-2 text-sm" value={routerName} onChange={(event) => onRouter(event.target.value as "local" | "typesafe")} disabled={active}>
      <option value="local">Local screening</option>
      <option value="typesafe">TypeSafe</option>
    </select>
    <label className="flex items-center gap-2 text-sm text-ink-muted"><input type="checkbox" checked={refineWithAstra} onChange={(event) => onRefine(event.target.checked)} disabled={active} />Ask Astra for layout improvements</label>
    <Button variant="quiet" onClick={onRun} disabled={active}>Run 1,000 route trials</Button>
  </div>;
}

function TrialProgress({ status }: { status: SimulationStatus | null }) {
  if (!status || !isActive(status)) return null;
  return <div className="space-y-1" role="status">
    <progress aria-label="Route trial progress" className="h-2 w-full" value={status.completed} max={status.samples} />
    <p className="text-sm text-ink-muted">Processed {status.completed} of {status.samples} route trials.</p>
  </div>;
}

function downloadCandidate(graph: SceneGraph) {
  const href = URL.createObjectURL(new Blob([JSON.stringify(graph, null, 2)], { type: "application/json" }));
  const link = document.createElement("a");
  link.href = href;
  link.download = "standardphysics-candidate-layout.json";
  link.click();
  URL.revokeObjectURL(href);
}

function ResultIntroduction({ result, status }: { result: NonNullable<SimulationStatus["result"]>; status: SimulationStatus }) {
  const screening = status.router === "typesafe" ? "TypeSafe" : "Local screening";
  const preview = result.preview ? "This is an unverified preview for review; it does not apply any layout changes." : "No layout changes were applied.";
  const mesh = result.mesh_checked ? "Measured mesh collisions were screened." : "Measured mesh collision screening was unavailable.";
  return <>
    <p>Processed {status.completed} of {result.total_runs} trials across {result.unique_layouts} distinct layouts. {result.rejected_runs} routing decisions were rejected.</p>
    <p className="text-ink-muted">Screened with {screening}. Rules checked: {result.rules_checked} of {result.rules_total}.</p>
    <p className="text-ink-muted">Provider calls: {result.typesafe_calls} TypeSafe and {result.astra_calls} Astra. Deterministic exhaustive evaluations: {result.exhaustive_evaluations.toLocaleString()}.</p>
    <p className="text-ink-muted">{preview} {mesh}</p>
  </>;
}

function PhysicsResults({ result, labels }: { result: NonNullable<SimulationStatus["result"]>; labels: Map<string, string> }) {
  const physics = result.physics;
  if (!physics) return null;
  const barriers = physics.observations.filter((item) => item.status !== "clear");
  const blockedRoutes = physics.routes.filter((route) => !route.reachable);
  return <details className="rounded-lg bg-rule/30 p-3" open>
    <summary className="cursor-pointer font-medium">Wheelchair physics and environment routes</summary>
    <div className="mt-3 space-y-2 text-sm">
      <p className="text-ink-muted">One-inch analysis; {physics.mesh_triangles_checked.toLocaleString()} mesh triangles, {physics.surface_samples.toLocaleString()} low-surface samples, {physics.seats_found} seats, {physics.cashiers_found} service points, and {physics.exits_found} exits.</p>
      <p className="text-ink-muted">{physics.routes.length} customer routes screened between every door, opening, and piece of furniture; {blockedRoutes.length} were unreachable.</p>
      {barriers.length > 0 && <ul className="space-y-2">{barriers.map((item, index) => {
        const nodes = item.node_ids.map((id) => labels.get(id) ?? id);
        const value = item.measured_value === null ? "" : `: ${item.measured_value.toFixed(2)} ${item.unit ?? ""}`;
        return <li key={`${item.kind}-${index}`} className="rounded-md border border-rule p-2">
          <p className="font-medium">{item.title}{value}</p>
          <p className="text-ink-muted">{item.status.replaceAll("_", " ")}{nodes.length > 0 ? `; ${nodes.join(", ")}` : ""}</p>
        </li>;
      })}</ul>}
    </div>
  </details>;
}

function ResultFeedback({ feedback, labels }: { feedback: SimulationFeedback[]; labels: Map<string, string> }) {
  if (feedback.length === 0) return null;
  return <details className="rounded-lg bg-rule/30 p-3"><summary className="cursor-pointer font-medium">Profile failures and blockers</summary><ul className="mt-3 space-y-2">{feedback.map((item) => <Feedback key={`${item.workflow_title}-${item.profile_title}`} feedback={item} labels={labels} />)}</ul></details>;
}

function ResultLimitations({ limitations }: { limitations: string[] }) {
  if (limitations.length === 0) return null;
  return <ul className="list-disc space-y-1 pl-5 text-ink-muted">{limitations.map((limitation) => <li key={limitation}>{limitation}</li>)}</ul>;
}

function CandidateDownload({ graph }: { graph: SceneGraph | null }) {
  if (!graph) return null;
  return <Button variant="quiet" onClick={() => downloadCandidate(graph)}>Download candidate layout JSON</Button>;
}

function AstraRedesign({ result }: { result: NonNullable<SimulationStatus["result"]> }) {
  if (!result.redesign_model) return null;
  return <div className="space-y-1 rounded-lg bg-rule/30 p-3 text-sm">
    <p className="font-medium">Astra layout proposal {result.redesign_accepted ? "accepted for preview" : "rejected"}</p>
    <p className="text-ink-muted">Model: {result.redesign_model}</p>
    <p className="text-ink-muted">Adaptive rounds attempted: {result.adaptive_rounds.length}.</p>
    {result.redesign_reasons.length > 0 && <ul className="list-disc space-y-1 pl-5 text-ink-muted">{result.redesign_reasons.map((reason) => <li key={reason}>{reason}</li>)}</ul>}
  </div>;
}

function SimulationResults({ status, labels, scene, onTryLayout }: { status: SimulationStatus | null; labels: Map<string, string>; scene: SceneGraph; onTryLayout: (moves: NodeMove[]) => void }) {
  if (!status?.result) return null;
  const moves = status.result.recommended_graph && candidateMoves(scene, status.result.recommended_graph);
  return <div className="space-y-3 text-sm">
    <ResultIntroduction result={status.result} status={status} />
    <PhysicsResults result={status.result} labels={labels} />
    <ResultFeedback feedback={status.result.feedback} labels={labels} />
    <ResultLimitations limitations={status.result.limitations} />
    <AstraRedesign result={status.result} />
    {moves && moves.length > 0 && <Button variant="quiet" onClick={() => onTryLayout(moves)}>Preview candidate in room</Button>}
    <CandidateDownload graph={status.result.recommended_graph} />
  </div>;
}

function useSimulation(scanId: string, revision: number) {
  const router = useRouter();
  const [routerName, setRouterName] = useState<"local" | "typesafe">("local");
  const [refineWithAstra, setRefineWithAstra] = useState(false);
  const [status, setStatus] = useState<SimulationStatus | null>(null);
  const [rebuilding, setRebuilding] = useState(false);
  const [starting, setStarting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const active = isActive(status);

  useEffect(() => {
    let stale = false;
    let pending = false;
    async function refresh() {
      if (pending) return;
      pending = true;
      try {
        const next = await getSimulation(scanId, revision);
        if (!stale) setStatus(next);
      } catch (reason) {
        if (!stale && !(reason instanceof SimulationRequestError && reason.status === 404)) {
          setError(message(reason, "We couldn't update the route trials."));
        }
      }
      finally { pending = false; }
    }
    void refresh();
    if (!active) return () => { stale = true; };
    const timer = setInterval(() => {
      void refresh();
    }, POLL_MS);
    return () => { stale = true; clearInterval(timer); };
  }, [scanId, revision, active]);

  async function rebuild() {
    setRebuilding(true);
    setError(null);
    try {
      await rebuildRoom(scanId, revision);
      router.refresh();
    } catch (reason) {
      setError(message(reason, "We couldn't rebuild this room."));
    } finally {
      setRebuilding(false);
    }
  }

  async function run() {
    setError(null);
    setStarting(true);
    try {
      setStatus(await startSimulation(scanId, {
        base_revision: revision,
        samples: SAMPLES,
        max_workers: 4,
        router: routerName,
        refine_with_astra: refineWithAstra,
        typesafe_call_limit: 3000,
        astra_rounds: 4,
        exhaustive_evaluations: 0,
      }));
    } catch (reason) {
      setError(message(reason, "We couldn't start the route trials."));
    } finally {
      setStarting(false);
    }
  }

  return { routerName, setRouterName, refineWithAstra, setRefineWithAstra, status, rebuilding, starting, error, rebuild, run };
}

export function SimulationPanel({ scanId, scene, onTryLayout }: { scanId: string; scene: SceneGraph; onTryLayout: (moves: NodeMove[]) => void }) {
  const simulation = useSimulation(scanId, scene.revision);
  const labels = useMemo(() => new Map(scene.nodes.map((node) => [node.id, node.label])), [scene.nodes]);
  return (
    <section className="space-y-3 px-3 py-4" aria-label="Rebuild and route trials">
      <div className="space-y-1">
        <h2 className="font-semibold">Rebuild and route trials</h2>
        <Link className="inline-block py-2 text-sm text-accent underline underline-offset-4" href={`/scans/${scanId}/replay?revision=${scene.revision}`}>Watch recorded runs</Link>
        <p className="text-sm text-ink-muted">Rebuild creates clean, selectable furniture from the scan. Astra can suggest labels and finishes when connected. Shapes and finishes are visual approximations; checks use measured dimensions.</p>
      </div>
      <SimulationControls routerName={simulation.routerName} refineWithAstra={simulation.refineWithAstra} rebuilding={simulation.rebuilding} active={isActive(simulation.status) || simulation.starting} onRouter={simulation.setRouterName} onRefine={simulation.setRefineWithAstra} onRebuild={simulation.rebuild} onRun={simulation.run} />
      <TrialProgress status={simulation.status} />
      {simulation.status?.error && <p role="alert" className="text-sm text-problem">{simulation.status.error}</p>}
      {simulation.error && <p role="alert" className="text-sm text-problem">{simulation.error}</p>}
      <SimulationResults status={simulation.status} labels={labels} scene={scene} onTryLayout={onTryLayout} />
    </section>
  );
}
