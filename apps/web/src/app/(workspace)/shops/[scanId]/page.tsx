import { headers } from "next/headers";
import { notFound } from "next/navigation";
import { OwnerView } from "@/components/owner/OwnerView";
import { RefreshWhile } from "@/components/RefreshWhile";
import { getAssessment, getChecklist, getJourney, getPathSuggestion, getRequests, getScan, getScenario, getScene, readyGlbUrl } from "@/lib/api";
import { isAppUserAgent } from "@/lib/native-bridge";
import { defaultPlaces, isWaiting } from "@/lib/owner-journey";
import { requireSession } from "@/lib/session";

export const dynamic = "force-dynamic";

const NO_CHECKLIST = { items: [], done: 0, total: 0 };

/** The owner's view of one shop: the one next step, then the results, the checklist, sharing and the tools. */
export default async function OwnerShopPage({ params }: PageProps<"/shops/[scanId]">) {
  const session = await requireSession();
  const { scanId } = await params;
  const [scan, journey] = await Promise.all([getScan(scanId), getJourney(scanId)]);
  if (!scan || !journey) notFound();
  const [requests, scene, assessment, checklist, scenario] = await Promise.all([
    getRequests(scanId), getScene(scanId), getAssessment(scanId), getChecklist(scanId), getScenario(scanId),
  ]);
  const places = defaultPlaces(requests);
  const [glbUrl, suggestedPath] = await Promise.all([
    scene ? readyGlbUrl(scanId) : null,
    journey.next_step.kind === "counter" || journey.next_step.kind === "path" ? getPathSuggestion(scanId, places) : null,
  ]);
  const embedded = isAppUserAgent((await headers()).get("user-agent"));
  return (
    <>
      <RefreshWhile pending={isWaiting(journey) || scan.state === "checking"} />
      <OwnerView
        scan={scan}
        journey={journey}
        requests={requests}
        scene={scene}
        glbUrl={glbUrl}
        assessment={assessment}
        checklist={checklist ?? NO_CHECKLIST}
        suggestedPath={suggestedPath}
        scenario={scenario}
        defaultPlaces={places}
        guest={session.guest}
        embedded={embedded}
      />
    </>
  );
}
