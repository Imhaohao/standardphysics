import { notFound } from "next/navigation";
import { Workspace } from "@/components/workspace/Workspace";
import { getAssessment, getScan, getScene, sceneGlbUrl } from "@/lib/api";
import { API_ORIGIN } from "@/lib/api-origin";
import { scanStatus } from "@/lib/scan-status";

export const dynamic = "force-dynamic";

async function glbAvailable(scanId: string): Promise<boolean> {
  const response = await fetch(`${API_ORIGIN}${sceneGlbUrl(scanId)}`, { cache: "no-store" });
  await response.body?.cancel();
  return response.ok;
}

async function loadPrevious(scanId: string, revision: number) {
  const [scene, assessment] = await Promise.all([getScene(scanId, revision), getAssessment(scanId, revision)]);
  return scene ? { scene, assessment } : null;
}

export default async function ShopPage({ params }: PageProps<"/scans/[scanId]">) {
  const { scanId } = await params;
  const scan = await getScan(scanId);
  if (!scan) notFound();
  const [scene, assessment, hasGlb] = await Promise.all([getScene(scanId), getAssessment(scanId), glbAvailable(scanId)]);

  if (!scene) {
    return (
      <main className="mx-auto max-w-2xl px-5 py-20">
        <h1 className="text-3xl font-bold">{scan.name}</h1>
        <p className="mt-4 text-lg text-ink-muted">{scanStatus(scan, null)}</p>
      </main>
    );
  }

  const exported = scene.revision === 0 ? scene : ((await getScene(scanId, 0)) ?? scene);
  const previous = scene.revision === 0 ? null : await loadPrevious(scanId, scene.revision - 1);
  return (
    <Workspace
      scan={scan}
      scene={scene}
      exported={exported}
      assessment={assessment}
      previous={previous}
      glbUrl={hasGlb ? sceneGlbUrl(scanId) : null}
    />
  );
}
