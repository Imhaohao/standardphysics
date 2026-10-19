import { FeaturedSheet } from "@/components/home/FeaturedSheet";
import { HomeTitleBlock } from "@/components/home/HomeTitleBlock";
import { SheetIndex } from "@/components/home/SheetIndex";
import { SheetPage } from "@/components/sheet/SheetPage";
import { SAMPLE_SCANS } from "@/fixtures/sample";
import { getApi } from "@/lib/api/client";
import { fixtureApi } from "@/lib/api/fixtureApi";
import { sessionToken } from "@/lib/session";
import { loadShopSheet, sheetNumber } from "@/lib/shopSheet";

export const dynamic = "force-dynamic";

async function homeSheets(token: string | null) {
  if (!token) return Promise.all(SAMPLE_SCANS.map((scan) => loadShopSheet(fixtureApi, scan)));
  const api = getApi(token);
  return Promise.all((await api.listScans()).map((scan) => loadShopSheet(api, scan)));
}

function heading(signedIn: boolean, count: number) {
  if (!signedIn) return "Find what blocks customers in your shop";
  return count > 1 ? "Your shops" : "Your shop";
}

export default async function HomePage() {
  const token = await sessionToken();
  const signedIn = token !== null;
  const [featured, ...others] = await homeSheets(token);

  return (
    <SheetPage className="grid gap-8 lg:min-h-full lg:grid-cols-[minmax(0,1fr)_20rem] lg:gap-10">
      <div className="flex min-w-0 flex-col gap-6">
        <h1 className="heading-display max-w-4xl text-5xl sm:text-7xl">{heading(signedIn, others.length + 1)}</h1>
        {featured ? (
          <FeaturedSheet sheet={featured} sheetNumber={sheetNumber(0)} actionLabel={signedIn ? "Open the shop" : "Open the sample shop"} />
        ) : (
          <EmptySheet />
        )}
        {others.length > 0 && <SheetIndex sheets={others} firstIndex={1} title="Other shops" />}
      </div>
      <HomeTitleBlock signedIn={signedIn} className="lg:self-end" />
    </SheetPage>
  );
}

function EmptySheet() {
  return (
    <div data-ink-avoid className="flex h-72 flex-col items-center justify-center gap-2 border border-dashed border-ink px-6 text-center sm:h-[26rem]">
      <p className="heading-display text-2xl">No drawings yet</p>
      <p className="max-w-sm text-ink-muted text-pretty">Scan your shop with an iPhone and its floor plan shows up here, measured to the inch.</p>
    </div>
  );
}
