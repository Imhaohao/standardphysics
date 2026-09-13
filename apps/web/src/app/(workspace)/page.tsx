import Link from "next/link";
import { FloorPlan } from "@/components/FloorPlan";
import { ScanShopButton } from "@/components/ScanShopButton";
import { getAssessment, getScenario, getScene, listScans } from "@/lib/api";
import { countNeedingAttention } from "@/lib/findings";
import { scanStatus } from "@/lib/scan-status";
import type { Scan } from "@/types/contracts";

export const dynamic = "force-dynamic";

const dateFormat = new Intl.DateTimeFormat("en-US", { month: "long", day: "numeric", year: "numeric" });

async function ShopRow({ scan }: { scan: Scan }) {
  const [scene, assessment, scenario] = await Promise.all([getScene(scan.id), getAssessment(scan.id), getScenario(scan.id)]);
  const needsWork = assessment !== null && assessment.rules_checked !== 0 && countNeedingAttention(assessment.findings) > 0;

  return (
    <li>
      <Link
        href={`/scans/${scan.id}`}
        className="group grid grid-cols-[7rem_1fr] items-center gap-6 rounded-xl p-3 transition-colors hover:bg-sheet sm:grid-cols-[9rem_1fr]"
      >
        <div className="aspect-square rounded-lg bg-rule/40 p-3">
          {scene && <FloorPlan scene={scene} className="h-full w-full" />}
        </div>
        <div className="min-w-0">
          <h2 className="truncate text-xl font-semibold">{scan.name}</h2>
          <p className="mt-1 text-ink-muted">{dateFormat.format(new Date(scan.created_at))}</p>
          <p className={`mt-3 flex items-center gap-2 font-medium ${needsWork ? "text-ink" : "text-ink-muted"}`}>
            {needsWork && <span className="size-2 rounded-full bg-problem" aria-hidden />}
            {scanStatus(scan, assessment, scenario !== null)}
          </p>
        </div>
      </Link>
    </li>
  );
}

export default async function SpacesPage() {
  const scans = await listScans();

  return (
    <main className="mx-auto max-w-2xl px-5 py-12 sm:py-20">
      <h1 className="text-3xl font-bold">Your shops</h1>
      {scans.length === 0 ? (
        <div className="mt-10">
          <ScanShopButton />
        </div>
      ) : (
        <>
          <ul className="-mx-3 mt-8 flex flex-col gap-2">
            {scans.map((scan) => (
              <ShopRow key={scan.id} scan={scan} />
            ))}
          </ul>
          <div className="mt-12">
            <ScanShopButton />
          </div>
        </>
      )}
    </main>
  );
}
