import type { Metadata } from "next";
import Link from "next/link";
import { notFound } from "next/navigation";
import { cache } from "react";
import { PrintButton } from "@/components/report/PrintButton";
import { ReportBody } from "@/components/report/ReportBody";
import { WhatWeChecked } from "@/components/report/WhatWeChecked";
import { RULEPACK_COVERAGE } from "@/lib/coverage";
import { SheetPage } from "@/components/sheet/SheetPage";
import { ShopHeader } from "@/components/shop/ShopHeader";
import { getApi } from "@/lib/api/client";
import { shopName } from "@/lib/shopSheet";

export const dynamic = "force-dynamic";

/** A read-only link needs no session: the token is the permission. */
const loadShared = cache(async (token: string) => (await getApi(null).getShared(token)) ?? notFound());

export async function generateMetadata({ params }: PageProps<"/r/[token]">): Promise<Metadata> {
  const { scan } = await loadShared((await params).token);
  return { title: `Accessibility report for ${shopName(scan)}`, robots: { index: false, follow: false }, referrer: "no-referrer" };
}

export default async function SharedReportPage({ params }: PageProps<"/r/[token]">) {
  const { scan, report, scene } = await loadShared((await params).token);
  return (
    <SheetPage className="flex flex-col gap-8">
      <ShopHeader title={`Accessibility report for ${shopName(scan)}`}>
        <PrintButton />
      </ShopHeader>
      <p className="-mt-4 max-w-3xl text-pretty text-ink-muted">
        The owner shared this read-only copy from{" "}
        <Link href="/" className="font-medium text-ink underline decoration-ink/30 underline-offset-4 hover:decoration-ink">
          Standard Physics
        </Link>
        . It stays up to date as they answer questions, and stops opening if they turn the link off.
      </p>
      <ReportBody scanId={scan.id} initialReport={report} scene={scene} readOnly>
        <WhatWeChecked coverage={RULEPACK_COVERAGE} />
      </ReportBody>
    </SheetPage>
  );
}
