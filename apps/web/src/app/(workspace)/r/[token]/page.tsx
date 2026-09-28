import type { Metadata } from "next";
import { cache } from "react";
import { PrintButton } from "@/components/PrintButton";
import { ReportDocument } from "@/components/report/ReportDocument";
import { SharedReportGone } from "@/components/report/SharedReportGone";
import { readSharedReport } from "@/components/report/sharedReport";
import { Wordmark } from "@/components/report/Wordmark";
import { fetchApi } from "@/lib/api-fetch";
import { API_ORIGIN } from "@/lib/api-origin";

export const dynamic = "force-dynamic";

const loadSharedReport = cache(async (token: string) =>
  readSharedReport(await fetchApi(`${API_ORIGIN}/api/shared/${encodeURIComponent(token)}`, { cache: "no-store" })),
);

/** The token is the whole key to the report, so the page stays out of search and never sends itself as a referrer. */
const PRIVATE_LINK: Metadata = { robots: { index: false, follow: false }, referrer: "no-referrer" };

export async function generateMetadata({ params }: PageProps<"/r/[token]">): Promise<Metadata> {
  const shared = await loadSharedReport((await params).token);
  const title = shared.kind === "report" ? `Report for ${shared.report.scan.name}` : "Standard Physics";
  return { ...PRIVATE_LINK, title };
}

export default async function SharedReportPage({ params, searchParams }: PageProps<"/r/[token]">) {
  const { token } = await params;
  const { plan } = await searchParams;
  const shared = await loadSharedReport(token);
  if (shared.kind === "gone") return <SharedReportGone message={shared.message} />;

  return (
    <ReportDocument
      report={shared.report}
      showScope={false}
      planId={typeof plan === "string" ? plan : undefined}
      pagePath={`/r/${encodeURIComponent(token)}`}
      modelBase={`/api/shared/${encodeURIComponent(token)}/architecture.stl`}
      toolbar={
        <>
          <Wordmark />
          <PrintButton purpose="pdf" />
        </>
      }
    />
  );
}
