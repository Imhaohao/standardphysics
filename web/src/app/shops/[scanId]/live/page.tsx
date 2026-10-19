import type { Metadata } from "next";
import { LiveSheet } from "@/components/live/LiveSheet";
import type { LiveSource } from "@/components/live/useLiveScan";
import { SheetPage } from "@/components/sheet/SheetPage";
import { ShopHeader } from "@/components/shop/ShopHeader";
import { isFixtureMode } from "@/lib/api/config";
import { loadOwnedShop } from "@/lib/loadShop";
import { shopName, type ShopSheet } from "@/lib/shopSheet";

export const dynamic = "force-dynamic";
export const metadata: Metadata = { title: "Live scan" };

function liveSource(sheet: ShopSheet, signedIn: boolean): LiveSource | null {
  const inProgress = sheet.scan.status === "capturing" || sheet.scan.status === "finishing";
  if (inProgress && signedIn && !isFixtureMode()) return { kind: "socket", scanId: sheet.scan.id };
  if (sheet.scene && sheet.report) return { kind: "replay", scanId: sheet.scan.id, scene: sheet.scene, report: sheet.report };
  return null;
}

export default async function LivePage({ params }: PageProps<"/shops/[scanId]/live">) {
  const { sheet, token } = await loadOwnedShop((await params).scanId);
  const source = liveSource(sheet, token !== null);
  const back = { backHref: sheet.href, backLabel: `Back to ${shopName(sheet.scan)}` };
  return (
    <SheetPage className="flex flex-col gap-8">
      {source ? (
        <LiveSheet source={source} reportHref={`${sheet.href}/report`} {...back} />
      ) : (
        <>
          <ShopHeader {...back} title="Live scan" />
          <p data-ink-avoid className="text-lg text-ink-muted">There&rsquo;s nothing to show yet. Start a scan in the app and it draws itself here as you walk.</p>
        </>
      )}
    </SheetPage>
  );
}
