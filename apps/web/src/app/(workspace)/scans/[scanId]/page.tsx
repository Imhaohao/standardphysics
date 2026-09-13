import { notFound } from "next/navigation";
import { RefreshWhile } from "@/components/RefreshWhile";
import { Workspace } from "@/components/workspace/Workspace";
import { getAssessment, getScan, getScenario, getScenarioSuggestion, getScene, sceneGlbUrl } from "@/lib/api";
import { API_ORIGIN } from "@/lib/api-origin";
import { scanStatus } from "@/lib/scan-status";
import type { Scan, SceneGraph } from "@/types/contracts";

export const dynamic = "force-dynamic";

/** Whether a GLB exists, and the revision whose layout it was exported from. */
async function glbExportedRevision(scanId: string): Promise<number | null> {
  const response = await fetch(`${API_ORIGIN}${sceneGlbUrl(scanId)}`, { method: "HEAD", cache: "no-store" });
  const revision = response.headers.get("X-Exported-Revision");
  return response.ok && revision !== null ? Number(revision) : null;
}

async function loadPrevious(scanId: string, revision: number) {
  const [scene, assessment] = await Promise.all([getScene(scanId, revision), getAssessment(scanId, revision)]);
  return scene ? { scene, assessment } : null;
}

async function loadExported(scanId: string, scene: SceneGraph, glbRevision: number | null): Promise<SceneGraph> {
  if (glbRevision === null || glbRevision === scene.revision) return scene;
  return (await getScene(scanId, glbRevision)) ?? scene;
}

function NotMeasuredYet({ scan }: { scan: Scan }) {
  return (
    <main className="mx-auto max-w-2xl px-5 py-20">
      <h1 className="text-3xl font-bold">{scan.name}</h1>
      <p className="mt-4 text-lg text-ink-muted">{scanStatus(scan, null)}</p>
      <RefreshWhile pending={scan.state !== "failed"} />
    </main>
  );
}

export default async function ShopPage({ params }: PageProps<"/scans/[scanId]">) {
  const { scanId } = await params;
  const scan = await getScan(scanId);
  if (!scan) notFound();
  const [scene, glbRevision] = await Promise.all([getScene(scanId), glbExportedRevision(scanId)]);
  if (!scene) return <NotMeasuredYet scan={scan} />;

  const [assessment, exported, previous, scenario] = await Promise.all([
    getAssessment(scanId, scene.revision),
    loadExported(scanId, scene, glbRevision),
    scene.revision === 0 ? null : loadPrevious(scanId, scene.revision - 1),
    getScenario(scanId),
  ]);
  const suggestedScenario = scenario ? null : await getScenarioSuggestion(scanId);
  return (
    <Workspace
      scan={scan}
      scene={scene}
      exported={exported}
      assessment={assessment}
      previous={previous}
      glbUrl={glbRevision === null ? null : sceneGlbUrl(scanId)}
      scenario={scenario}
      suggestedScenario={suggestedScenario}
      lidarUrl={scan.artifacts.some((artifact) => artifact.kind === "lidar_mesh") ? `/api/scans/${scanId}/lidar-mesh` : null}
    />
  );
}
