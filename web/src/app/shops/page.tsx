import type { Metadata } from "next";
import { ShopCard } from "@/components/shop/ShopCard";
import { SheetPage } from "@/components/sheet/SheetPage";
import { loadShopSheet, sheetNumber } from "@/lib/shopSheet";
import { ownerApi } from "@/lib/session";

export const dynamic = "force-dynamic";
export const metadata: Metadata = { title: "Your shops" };

export default async function ShopsPage() {
  const { api } = await ownerApi();
  const sheets = await Promise.all((await api.listScans()).map((scan) => loadShopSheet(api, scan)));
  return (
    <SheetPage className="flex flex-col gap-8">
      <h1 className="heading-display text-5xl sm:text-7xl">{sheets.length === 1 ? "Your shop" : "Your shops"}</h1>
      {sheets.length === 0 ? (
        <p data-ink-avoid className="max-w-md text-lg text-ink-muted text-pretty">
          Nothing here yet. Scan your shop with the Standard Physics app and its floor plan shows up here within a minute of finishing.
        </p>
      ) : (
        <ul className="grid gap-6 sm:grid-cols-2 xl:grid-cols-3">
          {sheets.map((sheet, index) => (
            <ShopCard key={sheet.scan.id} sheet={sheet} sheetNumber={sheetNumber(index)} />
          ))}
        </ul>
      )}
    </SheetPage>
  );
}
