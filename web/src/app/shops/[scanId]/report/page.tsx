import type { Metadata } from "next";
import { PrintButton } from "@/components/report/PrintButton";
import { ReportBody } from "@/components/report/ReportBody";
import { SheetPage } from "@/components/sheet/SheetPage";
import { ShopHeader } from "@/components/shop/ShopHeader";
import { loadOwnedShop } from "@/lib/loadShop";
import { shopName } from "@/lib/shopSheet";

export const dynamic = "force-dynamic";

export async function generateMetadata({ params }: PageProps<"/shops/[scanId]/report">): Promise<Metadata> {
  const { sheet } = await loadOwnedShop((await params).scanId);
  return { title: `Accessibility report for ${shopName(sheet.scan)}` };
}

export default async function ReportPage({ params }: PageProps<"/shops/[scanId]/report">) {
  const { sheet } = await loadOwnedShop((await params).scanId);
  const { scan, scene, report } = sheet;
  return (
    <SheetPage className="flex flex-col gap-8">
      <ShopHeader backHref={sheet.href} backLabel={`Back to ${shopName(scan)}`} title={`Accessibility report for ${shopName(scan)}`}>
        <PrintButton />
      </ShopHeader>
      {report ? (
        <ReportBody scanId={scan.id} initialReport={report} scene={scene} />
      ) : (
        <p data-ink-avoid className="text-lg text-ink-muted">This shop hasn&rsquo;t been checked yet. The report appears here within a minute of the scan finishing.</p>
      )}
    </SheetPage>
  );
}
