import { FileText, Broadcast } from "@phosphor-icons/react/dist/ssr";
import type { Metadata } from "next";
import Link from "next/link";
import { ShopHeader } from "@/components/shop/ShopHeader";
import { ShopWorkspace } from "@/components/shop/ShopWorkspace";
import { SheetPage } from "@/components/sheet/SheetPage";
import { buttonClassName } from "@/components/ui/Button";
import { loadOwnedShop } from "@/lib/loadShop";
import { scanStatusCopy, shopName } from "@/lib/shopSheet";

export const dynamic = "force-dynamic";

export async function generateMetadata({ params }: PageProps<"/shops/[scanId]">): Promise<Metadata> {
  const { sheet } = await loadOwnedShop((await params).scanId);
  return { title: shopName(sheet.scan) };
}

export default async function ShopPage({ params }: PageProps<"/shops/[scanId]">) {
  const { sheet } = await loadOwnedShop((await params).scanId);
  const live = sheet.scan.status === "capturing" || sheet.scan.status === "finishing";
  return (
    <SheetPage className="flex flex-col gap-8">
      <ShopHeader backHref="/shops" backLabel="All shops" title={shopName(sheet.scan)}>
        <Link href={`${sheet.href}/live`} className={buttonClassName(live ? "primary" : "outline")}>
          <Broadcast size={18} aria-hidden />
          {live ? "Watch the scan live" : "Replay the scan"}
        </Link>
        {sheet.report && (
          <Link href={`${sheet.href}/report`} className={buttonClassName(live ? "outline" : "primary")}>
            <FileText size={18} aria-hidden />
            Read the full report
          </Link>
        )}
      </ShopHeader>
      <p className="-mt-4 text-lg text-ink-muted">{scanStatusCopy(sheet)}</p>
      {sheet.scene ? (
        <ShopWorkspace scene={sheet.scene} groups={sheet.groups} />
      ) : (
        <p data-ink-avoid className="text-ink-muted">The plan shows up here once the scan has been processed.</p>
      )}
    </SheetPage>
  );
}
